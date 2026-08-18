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
    compute_and_save_aop_dop
)
from POLARIZED_LUCID import (
    detect_lucid_camera,
    acquisition_lucid_rapide,   # <-- capture rapide (mosaïque brute uniquement)
    traiter_mosaic_lucid        # <-- traitement différé
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

# Processus JAI (mode POLARIZED, avec sleep)
def run_jai_process(command_queue, done_event, ready_event, path_jai, t0_shared,
                    latitude_deg, longitude_deg, time_queue=None):
    print("[JAI] Initialisation caméra JAI...")
    connection_ID = detect_camera()
    if not connection_ID:
        print("[JAI] Aucune caméra détectée")
        if command_queue: command_queue.put("STOP")
        return
    device = eb.PvDevice.CreateAndConnect(connection_ID)[1]
    if device is None: return
    stream = eb.PvStream.CreateAndOpen(connection_ID)[1]
    if stream is None: return

    device_params = device.GetParameters()
    for name, value in [("TriggerMode","Off"), ("TriggerSource","Software"),
                        ("PixelFormat","Mono8"), ("AcquisitionMode","SingleFrame")]:
        try: device_params.Get(name).SetValue(value)
        except: pass
    if isinstance(device, eb.PvDeviceGEV):
        try: device_params.Get("GevSCPSPacketSize").SetValue(1400)
        except: pass
        try: device_params.Get("GevSCPD").SetValue(800000)
        except: pass
        device.NegotiatePacketSize()
        device.SetStreamDestination(stream.GetLocalIPAddress(), stream.GetLocalPort())


    device.StreamEnable()
    print("[JAI] Stream activé")

    print("[JAI] Attente initialisation LUCID...")
    ready_event.wait(timeout=20.0)
    print("[JAI] LUCID prête — démarrage acquisition JAI")

    # --- Lire et afficher la température du capteur JAI ---
    try:
        temp_node = device_params.Get("DeviceTemperature")
        if temp_node is not None:
            # GetValue() retourne (PvResult, valeur)
            temp_val = temp_node.GetValue()[1]
            print(f"[JAI] Température capteur : {temp_val:.1f} °C")
        else:
            print("[JAI] Nœud DeviceTemperature non disponible.")
    except Exception as e:
        print(f"[JAI] Impossible de lire la température : {e}")


    t_mid_utc = acquisition_jai_4_images(
        device, stream, path_jai,
        t0_global=None,
        command_queue=command_queue,
        done_event=done_event,
        t0_shared=t0_shared,
        skip_processing=True
    )
    sun_az, sun_el = compute_solar_ephemeris(latitude_deg, longitude_deg, t_mid_utc)
    save_ephemeris_json(path_jai, t_mid_utc, latitude_deg, longitude_deg, sun_az, sun_el)
    if time_queue is not None:
        time_queue.put(t_mid_utc)
    device.StreamDisable()
    stream.Close()
    eb.PvStream.Free(stream)
    device.Disconnect()
    eb.PvDevice.Free(device)
    print("[JAI] Process JAI terminé")


# Processus LUCID (capture rapide uniquement)
def run_lucid_process(done_event, ready_event, path_lucid, t0_shared, done_queue_lucid):
    print("[LUCID] Initialisation caméra Lucid...")
    device_lucid, nodemap_lucid, tl_stream_nodemap_lucid = detect_lucid_camera()
    if device_lucid is None:
        ready_event.set()
        return
    print("[LUCID] Caméra prête. Signal envoyé à JAI.")
    ready_event.set()
    print("[LUCID] Attente du déclenchement par JAI...")
    done_event.wait(timeout=30.0)
    print("[LUCID] Déclenchement reçu — acquisition rapide")

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

    acquisition_lucid_rapide(
        device_lucid, nodemap_lucid, tl_stream_nodemap_lucid,
        path_lucid, gain_value=0, exposure_value=150
    )
    done_queue_lucid.put("DONE")
    print("[LUCID] Process Lucid terminé")


# MAIN
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

    t_debut = time.time()
    for acq_num in range(1, nb_acq + 1):
        print(f"\n{'='*60}")
        print(f" ACQUISITION {acq_num} / {nb_acq}")
        print(f"{'='*60}")

        debut_theorique = t_debut + (acq_num - 1) * intervalle_min * 60
        attente = debut_theorique - time.time()
        if attente > 0:
            print(f"Pause de {attente:.0f} secondes...")
            time.sleep(attente)

        now = datetime.now()
        session_name = now.strftime("%d.%m.%Y_%Hh%Mm%Ss")
        path_jai   = os.path.join(base_path, "Data", "JAI",   session_name)
        path_lucid = os.path.join(base_path, "Data", "LUCID", session_name)

        ready_event = mp.Event()
        done_event  = mp.Event()
        t0_shared   = mp.Value("d", 0.0)
        time_queue  = mp.Queue()
        done_queue_lucid = mp.Queue()

        print("[MAIN] Lancement process LUCID...")
        p_lucid = mp.Process(
            target=run_lucid_process,
            args=(done_event, ready_event, path_lucid, t0_shared, done_queue_lucid)
        )
        p_lucid.start()

        print("[MAIN] Lancement process JAI...")
        p_jai = mp.Process(
            target=run_jai_process,
            args=(None, done_event, ready_event, path_jai, t0_shared,
                  lat, lon, time_queue)
        )
        p_jai.start()

        p_jai.join()
        p_lucid.join()

        t_mid_utc = time_queue.get()
        done_queue_lucid.get()

        t_mid_local = t_mid_utc.astimezone()
        new_session = t_mid_local.strftime("%d.%m.%Y_%Hh%Mm%Ss")

        new_path_jai = os.path.join(base_path, "Data", "JAI", new_session)
        os.rename(path_jai, new_path_jai)
        print(f"[MAIN] Dossier JAI renommé : {new_path_jai}")

        new_path_lucid = os.path.join(base_path, "Data", "LUCID", new_session)
        os.rename(path_lucid, new_path_lucid)
        print(f"[MAIN] Dossier LUCID renommé : {new_path_lucid}")

        sun_az, sun_el = compute_solar_ephemeris(lat, lon, t_mid_utc)
        save_ephemeris_json(new_path_lucid, t_mid_utc, lat, lon, sun_az, sun_el)

        # Traitement différé Lucid (calculs à partir de la mosaïque brute)
        traiter_mosaic_lucid(new_path_lucid)
        # Traitement immédiat JAI
        compute_and_save_aop_dop(new_path_jai)

    print(f"\n[MAIN] Acquisition terminée ({nb_acq} acquisition(s)).") 