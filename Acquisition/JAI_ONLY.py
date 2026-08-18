import os
import sys
import time
import json
import numpy as np
import cv2
from datetime import datetime, timezone

import eBUS as eb
from eBUS import *

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors
from io import BytesIO
import imageio.v2 as im

from pysolar.solar import get_altitude, get_azimuth

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from JAI_motor_rotation import home, reach_angle
import elliptec



# ACQUISITION JAI SEULE

def acquisition_jai_4_images(device, stream, path_jai, t0_global=None, command_queue=None, done_event=None, t0_shared=None, skip_processing=False):
    os.makedirs(path_jai, exist_ok=True)

    print(f"Dossier JAI : {path_jai}")

    angles = [0, 45, 90, 135]
    jai_images = {}

    print("Homing...")
    home()

    # Aligner le polariseur sur l’axe x de la caméra (offset de 67.85°)
    controller = elliptec.Controller('/dev/ttyUSB0')
    ro = elliptec.Rotator(controller, address='0')
    ro.shift_angle(67.85)
    controller.close_connection()
    print("Offset de 67.85° appliqué, polariseur aligné avec l’axe x caméra.")
    ts = time.time()
    t_start_utc = datetime.now(timezone.utc)


    # PHASE 1 : CAPTURE EN RAM

    for i, angle in enumerate(angles):

        print(f"\n=== Angle {angle}° ===")
        if command_queue is not None:
            if i == 1:  # avant rotation vers 45°
                print("[SYNC] Commande AOPG envoyée avant rotation 45°")
                command_queue.put("AOPG")
            elif i == 2:  # avant rotation vers 90°
                print("[SYNC] Commande DOP envoyée avant rotation 90°")
                command_queue.put("DOP")
            elif i == 3:  # avant rotation vers 135°
                print("[SYNC] Commande RAW envoyée avant rotation 135°")
                command_queue.put("RAW")


        if i == 0:
            pass
            #reach_angle(0,0)
        else:
            reach_angle(45, angle)

        '''if i == 1 :
            done_event.wait(timeout=0.8)

        elif i in [2, 3] :
            print("[SYNC] Attente fin acquisition LUCID avant capture JAI")
            done_event.wait(timeout=0.7)'''


        controller = elliptec.Controller('/dev/ttyUSB0')
        ro = elliptec.Rotator(controller, address='0')
        real_angle = ro.get_angle()
        controller.close_connection()

        print(f"Angle réel : {real_angle}")

        # ----- Signal à LUCID en mode POLARIZED (avant la capture) -----
        if angle == 45 and done_event is not None and command_queue is None:
            done_event.set()
            print("[SYNC] Signal LUCID envoyé (après angle 45°)")

        time.sleep(0.1)

        buffer = eb.PvBuffer()
        buffer.Alloc(device.GetPayloadSize())
        stream.QueueBuffer(buffer)

        if angle == 0:
            t0_global = time.time()

            if t0_shared is not None:
                t0_shared.value = t0_global

        if i>0 and done_event is not None and command_queue is not None:
            done_event.wait(timeout=1.0) 
            if i==3 and done_event is not None:
                done_event.wait(timeout=1.6) 
               
            done_event.clear()

        device.GetParameters().Get("AcquisitionStart").Execute()
        time.sleep(0.1)

        result, pvbuffer, op_result = stream.RetrieveBuffer(6000)


        device.GetParameters().Get("AcquisitionStop").Execute()

        if result.IsOK() and op_result.IsOK():
            image = pvbuffer.GetImage()
            data = image.GetDataPointer()

            np_img = np.ctypeslib.as_array(
                data,
                shape=(image.GetHeight(), image.GetWidth())
            ).copy()

            jai_images[angle] = np_img

            '''if command_queue is not None :

                if angle == 0:
                    print("[SYNC] LUCID RAW juste après JAI 0°")
                    command_queue.put("RAW")

                elif angle == 45:
                    print("[SYNC] LUCID AOPG juste après JAI 45°")
                    command_queue.put("AOPG")

                elif angle == 90:
                    print("[SYNC] LUCID DOP juste après JAI 90°")
                    command_queue.put("DOP")'''



            '''if angle == 0 and start_event is not None:
                print("[SYNC] Signal envoyé à LUCID après capture JAI 0°")
                start_event.set()'''

            print(f"[RAM] Image JAI {angle}° stockée en RAM")

            if t0_global is not None:
                print(f"[TIME] JAI image {angle}° capturée à t = {time.time() - t0_global:.3f} s")

        else:
            print(f"Erreur acquisition : {result.GetCodeString()} / {op_result.GetCodeString()}")

        stream.AbortQueuedBuffers()
        while stream.GetQueuedBufferCount() > 0:
            stream.RetrieveBuffer()

        # Désactiver/réactiver le stream pour vider complètement
        device.StreamDisable()
        #time.sleep(0.1)
        device.StreamEnable()
        time.sleep(0.1)  # petit délai


        # ----- Pauses APRÈS la capture en mode POLARIZED -----
        if command_queue is None:
            if angle == 0:
                time.sleep(0.9)
            elif angle == 45:
                time.sleep(1.1)
            elif angle == 90:
                time.sleep(0.6)


    tf_capture = time.time()
    print(f"[MAIN] Time of JAI RAM acquisition: {tf_capture - ts:.3f} s")

    t_end_utc = datetime.now(timezone.utc)
    t_mid_utc = t_start_utc + (t_end_utc - t_start_utc) / 2


    # PHASE 2 : SAUVEGARDE APRÈS CAPTURE
    
    print("[JAI] Début sauvegarde des images depuis la RAM...")

    for angle in angles:
        if angle in jai_images:
            filename = os.path.join(path_jai, f"I_{angle}.tiff")
            cv2.imwrite(filename, jai_images[angle])
            print(f"Sauvegardée : {filename}")
        else:
            print(f"[WARNING] Image JAI {angle}° absente, non sauvegardée.")

    tf_save = time.time()
    print(f"[TIME] Sauvegarde images JAI terminée à t = {tf_save - ts:.3f} s")


    # PHASE 3 : CALCUL AOP / DOP SI TOUTES LES IMAGES EXISTENT

    expected_files = [os.path.join(path_jai, f"I_{a}.tiff") for a in angles]

    if not skip_processing:
        if all(os.path.exists(f) for f in expected_files):
            compute_and_save_aop_dop(path_jai)
        else:
            print("[WARNING] Calcul AoP/DoP ignoré : images JAI manquantes.")
    else:
        print("[JAI] Traitement différé, pas de calcul AoP/DoP maintenant.")
        for f in expected_files:
            if not os.path.exists(f):
                print(f"[MISSING] {f}")

    print("FIN JAI")

    return t_mid_utc


# CALCUL AOP / DOP JAI

def compute_and_save_aop_dop(path_jai):

    I0 = im.imread(os.path.join(path_jai, "I_0.tiff")).astype(np.float64)
    I45 = im.imread(os.path.join(path_jai, "I_45.tiff")).astype(np.float64)
    I90 = im.imread(os.path.join(path_jai, "I_90.tiff")).astype(np.float64)
    I135 = im.imread(os.path.join(path_jai, "I_135.tiff")).astype(np.float64)

    S0 = (I0 + I45 + I90 + I135) / 2
    S1 = I0 - I90
    S2 = I45 - I135

    Z_global = (S1 + 1j * S2) / S0

    dop = np.abs(Z_global)
    aopg = 0.5 * np.angle(S1 + 1j * S2)
    aopg_deg = np.mod(aopg * 180 / np.pi, 180)

    np.save(os.path.join(path_jai, "dop.npy"), dop)
    np.save(os.path.join(path_jai, "aop.npy"), aopg_deg)

    # DOP colorisé
    dop_uint8 = cv2.normalize(dop, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    dop_cm = cv2.applyColorMap(dop_uint8, cv2.COLORMAP_VIRIDIS)

    fig, ax = plt.subplots(figsize=(10, 2))
    fig.subplots_adjust(bottom=0.35)

    norm = colors.Normalize(vmin=0.0, vmax=1.0)
    cbar = plt.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap='viridis'),
        cax=ax,
        orientation='horizontal'
    )
    cbar.set_label('Degree of Polarization - DoP')

    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)

    buf.seek(0)
    colorbar_img = np.frombuffer(buf.getvalue(), dtype=np.uint8)
    colorbar_img = cv2.imdecode(colorbar_img, cv2.IMREAD_COLOR)

    colorbar_resized = cv2.resize(colorbar_img, (dop_cm.shape[1], 400))
    colorbar_resized = colorbar_resized.astype(dop_cm.dtype)

    dop_combined = cv2.vconcat([dop_cm, colorbar_resized])
    cv2.imwrite(os.path.join(path_jai, "DOP.png"), dop_combined)

    # AOP colorisé
    aop_uint8 = (aopg_deg * 255 / 180).astype(np.uint8)
    aop_cm = cv2.applyColorMap(aop_uint8, cv2.COLORMAP_HSV)

    fig, ax = plt.subplots(figsize=(10, 2))
    fig.subplots_adjust(bottom=0.35)

    norm = colors.Normalize(vmin=0.0, vmax=180.0)
    cbar = plt.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap='hsv'),
        cax=ax,
        orientation='horizontal'
    )
    cbar.set_label('Global Angle of Polarization - AoP (°)')

    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)

    buf.seek(0)
    colorbar_img = np.frombuffer(buf.getvalue(), dtype=np.uint8)
    colorbar_img = cv2.imdecode(colorbar_img, cv2.IMREAD_COLOR)

    colorbar_resized = cv2.resize(colorbar_img, (aop_cm.shape[1], 400))
    colorbar_resized = colorbar_resized.astype(aop_cm.dtype)

    aop_combined = cv2.vconcat([aop_cm, colorbar_resized])
    cv2.imwrite(os.path.join(path_jai, "AOP.png"), aop_combined)

    print("DoP et AoP JAI sauvegardés avec colorbar")

    # Calcul AoP local (AoPL), azimut et élévation (caméra JAI)
    # Paramètres de calibration propres à la JAI
    cx_jai = 1206.1704
    cy_jai = 1657.6711
    fx_jai = 10845.4425
    fy_jai = 10876.8867

    h, w = aopg_deg.shape
    X = np.tile(np.arange(w), (h, 1))
    Y = np.tile(np.arange(h).reshape(h, 1), (1, w))

    Xn = (X - cx_jai) / fx_jai
    Yn = (Y - cy_jai) / fy_jai

    # Azimut (0-360°)
    azimuth_rad = np.arctan2(Yn, Xn)
    azimuth_deg = np.degrees(azimuth_rad) % 360

    # Élévation (0° = horizon, 90° = zénith)
    r = np.sqrt(Xn**2 + Yn**2)
    elevation_deg = 90.0 - np.degrees(np.arctan(r))

    # AoP local
    phi_deg = azimuth_deg % 180
    phi_deg = np.nan_to_num(phi_deg)
    aopl_deg = np.mod(aopg_deg - phi_deg, 180)

    # Sauvegardes en .mat
    import scipy.io as sio  
    sio.savemat(os.path.join(path_jai, "aopl.mat"), {"AoPL": aopl_deg})
    sio.savemat(os.path.join(path_jai, "azimut.mat"), {"azimut": azimuth_deg})
    sio.savemat(os.path.join(path_jai, "elevation.mat"), {"elevation": elevation_deg})
    # Visualisation AoPL (colorisée)
    aopl_uint8 = (aopl_deg * 255 / 180).astype(np.uint8)
    aopl_cm = cv2.applyColorMap(aopl_uint8, cv2.COLORMAP_HSV)

    fig, ax = plt.subplots(figsize=(10, 2))
    fig.subplots_adjust(bottom=0.35)
    norm = colors.Normalize(vmin=0.0, vmax=180.0)
    cbar = plt.colorbar(plt.cm.ScalarMappable(norm=norm, cmap='hsv'), cax=ax, orientation='horizontal')
    cbar.set_label('Local Angle of Polarization - AoPL (°)')

    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)
    buf.seek(0)
    colorbar_img = np.frombuffer(buf.getvalue(), dtype=np.uint8)
    colorbar_img = cv2.imdecode(colorbar_img, cv2.IMREAD_COLOR)

    bar_height = 400
    colorbar_resized = cv2.resize(colorbar_img, (aopl_cm.shape[1], bar_height))
    colorbar_resized = colorbar_resized.astype(aopl_cm.dtype)

    aopl_combined = cv2.vconcat([aopl_cm, colorbar_resized])
    cv2.imwrite(os.path.join(path_jai, "AOPL.png"), aopl_combined)

    print("AoPL, azimut et élévation JAI sauvegardés avec colorbar")
    



# DÉTECTION JAI

def detect_camera():
    system = PvSystem()
    system.Find()

    for i in range(system.GetInterfaceCount()):
        interface = system.GetInterface(i)

        if interface.GetDeviceCount() > 0:
            device_info = interface.GetDeviceInfo(0)
            return device_info.GetConnectionID()

    return None



# EPHEMERIDE

def compute_solar_ephemeris(latitude_deg, longitude_deg, when_utc):
    elevation_deg = get_altitude(latitude_deg, longitude_deg, when_utc)
    azimuth_deg = get_azimuth(latitude_deg, longitude_deg, when_utc)
    return azimuth_deg, elevation_deg


def save_ephemeris_json(path_folder, acquisition_time_utc, latitude_deg, longitude_deg,
                        sun_azimuth_deg, sun_elevation_deg):
    os.makedirs(path_folder, exist_ok=True)

    ephemeris_data = {
        "acquisition_time_utc": acquisition_time_utc.isoformat(),
        "latitude_deg": latitude_deg,
        "longitude_deg": longitude_deg,
        "sun_azimuth_deg": float(sun_azimuth_deg),
        "sun_elevation_deg": float(sun_elevation_deg)
    }

    json_path = os.path.join(path_folder, "ephemeride.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(ephemeris_data, f, indent=4)

    print(f"Éphéméride sauvegardée : {json_path}")



# MAIN

if __name__ == "__main__":

    connection_ID = detect_camera()

    if not connection_ID:
        print("Aucune caméra JAI détectée")
        exit()

    device = eb.PvDevice.CreateAndConnect(connection_ID)[1]

    if device is None:
        print("Impossible de se connecter à la caméra JAI")
        exit()

    stream = eb.PvStream.CreateAndOpen(connection_ID)[1]

    if stream is None:
        print("Impossible d'ouvrir le stream JAI")
        device.Disconnect()
        eb.PvDevice.Free(device)
        exit()

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
            device_params.Get("GevSCPSPacketSize").SetValue(1400)
            print("[JAI] GevSCPSPacketSize = 1440")
        except Exception as e:
            print(f"[JAI] Impossible de régler GevSCPSPacketSize: {e}")

        try:
            device_params.Get("GevSCPD").SetValue(800000)
            print("[JAI] GevSCPD = 800000")
        except Exception as e:
            print(f"[JAI] Impossible de régler GevSCPD: {e}")

        device.NegotiatePacketSize()
        device.SetStreamDestination(stream.GetLocalIPAddress(), stream.GetLocalPort())

    device.StreamEnable()
    print("[JAI] Stream enabled and camera configured")
    time.sleep(0.2)


    # Coordonnées Luminy / Marseille
    latitude_deg = 43.2317
    longitude_deg = 5.4396

    now = datetime.now()
    session_name = now.strftime("%d.%m.%Y_%Hh%Mm%Ss")

    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path_jai = os.path.join(base_path, "Data", "JAI", session_name)

    t0_global = time.time()

    t_mid_utc = acquisition_jai_4_images(
        device,
        stream,
        path_jai,
        t0_global=t0_global
    )

    # Renommer le dossier avec l'heure locale correspondant au milieu de la séquence
    t_mid_local = t_mid_utc.astimezone()          # fuseau horaire local
    new_session = t_mid_local.strftime("%d.%m.%Y_%Hh%Mm%Ss")
    new_path_jai = os.path.join(base_path, "Data", "JAI", new_session)
    os.rename(path_jai, new_path_jai)
    path_jai = new_path_jai

    device.StreamDisable()
    stream.Close()
    eb.PvStream.Free(stream)

    device.Disconnect()
    eb.PvDevice.Free(device)

    print("Acquisition JAI terminée")