import os
import time
from datetime import datetime, timezone
import multiprocessing as mp
import tkinter as tk
from tkinter import messagebox

from JAI_ONLY import (
    detect_camera,
    acquisition_jai_4_images,
    compute_solar_ephemeris,
    save_ephemeris_json,
    compute_and_save_aop_dop          )
from LUCID_ONLY import (
    detect_lucid_camera,
    capture_lucid_aopg_ram,
    capture_lucid_dop_ram,
    capture_lucid_raw_ram,
    save_lucid_results
)

import eBUS as eb
from eBUS import *


def saisie_parametres():
    root = tk.Tk()
    root.title("Paramètres de mission")
    root.geometry("400x300")
    root.resizable(False, False)
    frame = tk.Frame(root)
    frame.place(relx=0.5, rely=0.5, anchor='center')

    tk.Label(frame, text="Latitude (degrés) :").pack(pady=2)
    entry_lat = tk.Entry(frame, width=25, justify='center')
    entry_lat.pack(pady=2)

    tk.Label(frame, text="Longitude (degrés) :").pack(pady=2)
    entry_lon = tk.Entry(frame, width=25, justify='center')
    entry_lon.pack(pady=2)

    # ---------- MODIFIÉ : durée totale en minutes ----------
    tk.Label(frame, text="Durée totale (minutes, >=1) :").pack(pady=2)
    entry_duree = tk.Entry(frame, width=25, justify='center')
    entry_duree.pack(pady=2)

    tk.Label(frame, text="Intervalle min (minutes, >=1) :").pack(pady=2)
    entry_inter = tk.Entry(frame, width=25, justify='center')
    entry_inter.pack(pady=2)

    result = {"lat": None, "lon": None, "duree_min": None, "intervalle": None}

    def valider():
        try:
            lat = float(entry_lat.get())
            lon = float(entry_lon.get())
            duree_min = float(entry_duree.get())      # maintenant en minutes
            intervalle = float(entry_inter.get())

            if duree_min < 1:
                messagebox.showerror("Erreur", "La durée totale doit être >= 1 minute.")
                return
            if intervalle < 1:
                messagebox.showerror("Erreur", "L'intervalle minimum doit être >= 1 minute.")
                return
            if duree_min < intervalle:
                messagebox.showerror("Erreur",
                    "La durée totale est inférieure à l'intervalle minimum.\nAucune acquisition possible.")
                return

            result["lat"] = lat
            result["lon"] = lon
            result["duree_min"] = duree_min
            result["intervalle"] = intervalle
            root.destroy()
        except:
            messagebox.showerror("Erreur", "Valeurs invalides ou champs vides. Vérifiez les formats.")

    def annuler():
        root.destroy()

    btn_frame = tk.Frame(frame)
    btn_frame.pack(pady=10)
    tk.Button(btn_frame, text="Lancer les acquisitions", command=valider,
              bg="green", fg="white", width=22).pack(pady=2)
    tk.Button(btn_frame, text="Annuler", command=annuler,
              bg="red", fg="white", width=22).pack(pady=2)

    root.mainloop()
    if result["lat"] is None:
        return None
    return result["lat"], result["lon"], result["duree_min"], result["intervalle"]

# Processus JAI – initialisation UNIQUE, boucle sur path_queue

def run_jai_process_loop(command_queue, lucid_done_event, lucid_ready_event,
                         t0_shared, time_queue, path_queue,
                         latitude_deg=43.2317, longitude_deg=5.4396):
    print("[JAI] Initialisation caméra JAI...")
    connection_ID = detect_camera()
    if not connection_ID:
        print("[JAI] Aucune caméra détectée")
        return

    device = eb.PvDevice.CreateAndConnect(connection_ID)[1]
    if device is None:
        print("[JAI] Impossible de se connecter")
        return

    stream = eb.PvStream.CreateAndOpen(connection_ID)[1]
    if stream is None:
        print("[JAI] Impossible d'ouvrir le stream")
        device.Disconnect()
        eb.PvDevice.Free(device)
        return

    device_params = device.GetParameters()
    for name, value in [
        ("TriggerMode", "Off"),
        ("TriggerSource", "Software"),
        ("PixelFormat", "Mono8"),
        ("AcquisitionMode", "SingleFrame")
    ]:
        try:
            device_params.Get(name).SetValue(value)
            print(f"[JAI] {name} = {value}")
        except Exception as e:
            print(f"[JAI] Impossible de régler {name}: {e}")

    if isinstance(device, eb.PvDeviceGEV):
        try:
            device_params.Get("GevSCPSPacketSize").SetValue(1440)
        except: pass
        try:
            device_params.Get("GevSCPD").SetValue(50000)
        except: pass
        device.NegotiatePacketSize()
        device.SetStreamDestination(
            stream.GetLocalIPAddress(),
            stream.GetLocalPort()
        )


    device.StreamEnable()
    print("[JAI] Caméra prête, en attente des acquisitions...")

    try:
        while True:
            path_jai = path_queue.get()
            if path_jai is None:
                print("[JAI] Signal d'arrêt reçu, fermeture.")
                break

            print(f"[JAI] Démarrage acquisition -> {path_jai}")

            # --- Lire et afficher la température du capteur JAI ---
            try:
                temp_node = device_params.Get("DeviceTemperature")
                if temp_node is not None:
                    temp_val = temp_node.GetValue()[1]   # eBUS retourne (PvResult, valeur)
                    print(f"[JAI] Température capteur : {temp_val:.1f} °C")
                else:
                    print("[JAI] Nœud DeviceTemperature non disponible.")
            except Exception as e:
                print(f"[JAI] Impossible de lire la température : {e}")


            print("[JAI] Attente initialisation LUCID...")
            lucid_ready_event.wait(timeout=20.0)
            print("[JAI] LUCID prête — démarrage acquisition JAI")

            t_mid_utc = acquisition_jai_4_images(
                device, stream, path_jai,
                t0_global=None,
                command_queue=command_queue,
                done_event=lucid_done_event,
                t0_shared=t0_shared,
                skip_processing=True
            )

            # Sauvegarde éphéméride JAI
            sun_az, sun_el = compute_solar_ephemeris(latitude_deg, longitude_deg, t_mid_utc)
            save_ephemeris_json(path_jai, t_mid_utc, latitude_deg, longitude_deg, sun_az, sun_el)
            print(f"[JAI] Éphéméride sauvegardée dans {path_jai}")

            time_queue.put(t_mid_utc)

            # Remettre les événements dans l'état initial pour la prochaine acquisition
            lucid_ready_event.clear()
            print("[JAI] Acquisition terminée.")
    finally:
        device.StreamDisable()
        stream.Close()
        eb.PvStream.Free(stream)
        device.Disconnect()
        eb.PvDevice.Free(device)
        print("[JAI] Ressources libérées.")


# Processus LUCID – initialisation UNIQUE, boucle sur path_queue

def run_lucid_process_loop(command_queue, lucid_done_event, lucid_ready_event,
                           t0_shared, path_queue, done_queue_lucid):
    print("[LUCID] Initialisation caméra Lucid...")
    device_lucid, nodemap_lucid, tl_stream_lucid = detect_lucid_camera()
    if device_lucid is None:
        print("[LUCID] Caméra non détectée.")
        return

    # Désactiver les automatismes AVANT de régler l'exposition
    exposure_auto_node = nodemap_lucid.get_node("ExposureAuto")
    if exposure_auto_node:
        exposure_auto_node.value = "Off"
    gain_auto_node = nodemap_lucid.get_node("GainAuto")
    if gain_auto_node:
        gain_auto_node.value = "Off"

    gain_node = nodemap_lucid.get_node("Gain")
    if gain_node:
        gain_node.value = float(0.0)
    expo_node = nodemap_lucid.get_node("ExposureTime")
    if expo_node:
        expo_node.value = 150.0   # µs

    tl_stream_lucid['StreamAutoNegotiatePacketSize'].value = True
    tl_stream_lucid['StreamPacketResendEnable'].value = True
    nodes = nodemap_lucid.get_node(['Width', 'Height'])
    nodes['Width'].value = nodes['Width'].max
    nodes['Height'].value = nodes['Height'].max

    print("[LUCID] Caméra prête, en attente des acquisitions...")

    try:
        while True:
            path_lucid = path_queue.get()
            if path_lucid is None:
                print("[LUCID] Signal d'arrêt reçu, fermeture.")
                break

            print(f"[LUCID] Démarrage acquisition -> {path_lucid}")

            os.makedirs(path_lucid, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            # Signaler que LUCID est prête
            lucid_ready_event.set()

            # --- Lire et afficher la température du capteur Lucid ---
            try:
                temp_node = nodemap_lucid.get_node("DeviceTemperature")
                if temp_node is not None:
                    temp_val = temp_node.value
                    print(f"[LUCID] Température capteur : {temp_val:.1f} °C")
                else:
                    print("[LUCID] Nœud DeviceTemperature non disponible.")
            except Exception as e:
                print(f"[LUCID] Impossible de lire la température : {e}")
            

            # Attendre et traiter les commandes AOPG, DOP, RAW
            lucid_data = {}
            for expected_cmd in ["AOPG", "DOP", "RAW"]:
                cmd_recu = command_queue.get()   # bloquant
                if cmd_recu == expected_cmd:
                    t0_global = t0_shared.value
                    if expected_cmd == "AOPG":
                        lucid_data["AOPG"] = capture_lucid_aopg_ram(device_lucid, nodemap_lucid, t0_global)
                    elif expected_cmd == "DOP":
                        lucid_data["DOP"] = capture_lucid_dop_ram(device_lucid, nodemap_lucid, t0_global)
                    elif expected_cmd == "RAW":
                        lucid_data["RAW"] = capture_lucid_raw_ram(device_lucid, nodemap_lucid, t0_global)
                    lucid_done_event.set()
                else:
                    print(f"[LUCID] Commande inattendue : {cmd_recu}")
                    break

            # Sauvegarde des résultats
            save_lucid_results(path_lucid, timestamp, lucid_data, gain_value=0, exposure_value=150)
            print("[LUCID] Acquisition terminée.")

            # Signaler au main que LUCID a fini (tous les fichiers sont écrits)
            done_queue_lucid.put("DONE")
    finally:
        print("[LUCID] Process Lucid terminé.")



# MAIN – Interface graphique, boucle temporelle, traitement immédiat

if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)

    params = saisie_parametres()
    if params is None:
        print("Mission annulée.")
        exit(1)
    lat, lon, duree_min, intervalle_min = params

    # Calcul direct avec la durée en minutes
    nb_acq = int(duree_min / intervalle_min)
    if nb_acq < 1:
        nb_acq = 1

    print(f"\nAcquisitions : {duree_min:.0f} min, intervalle >= {intervalle_min:.0f} min")
    print(f"Nombre d'acquisitions : {nb_acq}")

    base_path = "/media/raspberrypi/CORSAIR"

    #Objets de synchronisation (créés UNE SEULE FOIS) 
    command_queue     = mp.Queue()         # pour les commandes AOPG / DOP / RAW
    lucid_ready_event = mp.Event()         # LUCID → JAI : LUCID est initialisée
    lucid_done_event  = mp.Event()         # JAI ↔ LUCID : confirmation de capture
    t0_shared         = mp.Value("d", 0.0) # temps partagé
    time_queue        = mp.Queue()         # JAI → main : temps milieu UTC

    # Queues pour transmettre les chemins et la fin de LUCID
    path_queue_jai   = mp.Queue()
    path_queue_lucid = mp.Queue()
    done_queue_lucid = mp.Queue()

    # Lancement UNIQUE des processus 
    print("[MAIN] Lancement du processus JAI...")
    p_jai = mp.Process(
        target=run_jai_process_loop,
        args=(command_queue, lucid_done_event, lucid_ready_event,
              t0_shared, time_queue, path_queue_jai,
              lat, lon)   # les coordonnées saisies sont transmises
    )
    p_jai.start()

    print("[MAIN] Lancement du processus LUCID...")
    p_lucid = mp.Process(
        target=run_lucid_process_loop,
        args=(command_queue, lucid_done_event, lucid_ready_event,
              t0_shared, path_queue_lucid, done_queue_lucid)
    )
    p_lucid.start()

    # Boucle temporelle 
    t_debut = time.time()
    for acq_num in range(1, nb_acq + 1):
        print(f"\n{'='*60}")
        print(f" ACQUISITION {acq_num} / {nb_acq}")
        print(f"{'='*60}")

        # Respect de l'intervalle minimum
        debut_theorique = t_debut + (acq_num - 1) * intervalle_min * 60
        attente = debut_theorique - time.time()
        if attente > 0:
            print(f"Pause de {attente:.0f} secondes...")
            time.sleep(attente)

        now = datetime.now()
        session_name = now.strftime("%d.%m.%Y_%Hh%Mm%Ss")
        path_jai   = os.path.join(base_path, "Data", "JAI",   session_name)
        path_lucid = os.path.join(base_path, "Data", "LUCID", session_name)

        # Envoyer les chemins aux processus
        path_queue_jai.put(path_jai)
        path_queue_lucid.put(path_lucid)

        # Attendre la fin de l'acquisition JAI (le temps milieu arrive via time_queue)
        t_mid_utc = time_queue.get()

        # Attendre que LUCID ait terminé d'écrire ses fichiers
        done_queue_lucid.get()

        # Renommer les dossiers avec l'heure milieu (locale)
        t_mid_local = t_mid_utc.astimezone()
        new_session = t_mid_local.strftime("%d.%m.%Y_%Hh%Mm%Ss")

        new_path_jai = os.path.join(base_path, "Data", "JAI", new_session)
        os.rename(path_jai, new_path_jai)
        print(f"[MAIN] Dossier JAI renommé : {new_path_jai}")

        new_path_lucid = os.path.join(base_path, "Data", "LUCID", new_session)
        os.rename(path_lucid, new_path_lucid)
        print(f"[MAIN] Dossier LUCID renommé : {new_path_lucid}")

        # Éphéméride LUCID (optionnelle)
        sun_az, sun_el = compute_solar_ephemeris(lat, lon, t_mid_utc)
        save_ephemeris_json(new_path_lucid, t_mid_utc, lat, lon, sun_az, sun_el)

        # Traitement immédiat du dossier JAI 
        print(f"[MAIN] Traitement du dossier JAI : {new_path_jai}")
        compute_and_save_aop_dop(new_path_jai)

    #  Arrêt des processus 
    path_queue_jai.put(None)
    path_queue_lucid.put(None)
    p_jai.join()
    p_lucid.join()

    print(f"\n[MAIN] Acquisition terminée ({nb_acq} acquisition(s)).")