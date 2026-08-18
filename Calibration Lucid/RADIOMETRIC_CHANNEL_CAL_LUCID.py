#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calibration radiométrique de la caméra Lucid polarimétrique (DoFP).
Produit les canaux dark et les cartes de gain pour I0, I45, I90, I135.
"""

import os
import time
import numpy as np
import scipy.io as sio
from datetime import datetime
import cv2

# Pour la caméra Lucid
from arena_api.system import system

# ----------------------------------------------------------------------
# 1. Détection et initialisation de la caméra
# ----------------------------------------------------------------------
def detect_lucid_camera():
    device_infos = system.device_infos
    lucid_info = None
    for info in device_infos:
        if info["vendor"] == "Lucid Vision Labs":
            lucid_info = info
            break

    if lucid_info is None:
        print("Aucune caméra Lucid détectée")
        return None, None, None

    devices = system.create_device([lucid_info])
    if not devices:
        print("Impossible de créer le device Lucid")
        return None, None, None

    device = system.select_device(devices)
    nodemap = device.nodemap
    tl_stream_nodemap = device.tl_stream_nodemap

    # Lecture de la température (optionnel)
    temp_node = nodemap.get_node("DeviceTemperature")
    if temp_node is not None:
        print(f"Température caméra : {temp_node.value:.2f} °C")

    return device, nodemap, tl_stream_nodemap


# ----------------------------------------------------------------------
# 2. Extraction des 4 canaux de la mosaïque Sony
# ----------------------------------------------------------------------
def extract_channels(mosaic_16bit):
    """
    Motif Sony :
        [90°  45°]
        [135°  0°]
    Retourne I0, I45, I90, I135 en float64.
    """
    I0   = mosaic_16bit[1::2, 1::2].astype(np.float64)
    I45  = mosaic_16bit[0::2, 1::2].astype(np.float64)
    I90  = mosaic_16bit[0::2, 0::2].astype(np.float64)
    I135 = mosaic_16bit[1::2, 0::2].astype(np.float64)
    return I0, I45, I90, I135


# ----------------------------------------------------------------------
# 3. Capture de N images et moyennage
# ----------------------------------------------------------------------
def capture_average_mosaic(device, nodemap, tl_stream_nodemap,
                           num_images=15, gain_value=0, exposure_value=20000):
    """
    Capture num_images en PolarizeMono12, les accumule en float64,
    retourne la mosaïque moyenne en uint16.
    """
    # Configuration de la caméra
    gain_node = nodemap.get_node("Gain")
    if gain_node:
        gain_node.value = float(gain_value)

    tl_stream_nodemap['StreamAutoNegotiatePacketSize'].value = True
    tl_stream_nodemap['StreamPacketResendEnable'].value = True

    nodes = nodemap.get_node(['Width', 'Height', 'PixelFormat'])
    nodes['Width'].value = nodes['Width'].max
    nodes['Height'].value = nodes['Height'].max
    nodes['PixelFormat'].value = 'PolarizeMono12'

    width = nodes['Width'].value
    height = nodes['Height'].value

    print(f"Acquisition de {num_images} images (gain={gain_value} dB, expo={exposure_value} µs)...")
    sum_mosaic = np.zeros((height, width), dtype=np.float64)

    for i in range(num_images):
        with device.start_stream():
            image_buffer = device.get_buffer()
            raw_bytes = bytes(image_buffer.data)
            img = np.frombuffer(raw_bytes, dtype=np.uint16).reshape((height, width))
            device.requeue_buffer(image_buffer)
            device.stop_stream()
        sum_mosaic += img.astype(np.float64)
        if (i + 1) % 5 == 0:
            print(f"  {i+1}/{num_images}")

    avg_mosaic = np.round(sum_mosaic / num_images).astype(np.uint16)
    print("Moyenne terminée.")
    return avg_mosaic


# ----------------------------------------------------------------------
# 4. Programme principal de calibration
# ----------------------------------------------------------------------
def main():
    # Dossier de sauvegarde (à personnaliser)
    base_dir = os.path.join(os.getcwd(), "calibration_data")
    os.makedirs(base_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Paramètres fixes (à ajuster selon vos besoins)
    GAIN = 0          # dB
    EXPOSURE = 20000  # µs
    N_IMAGES = 15     # nombre d'images à moyenner

    # --- Initialisation caméra ---
    print("Initialisation de la caméra Lucid...")
    device, nodemap, tl_stream = detect_lucid_camera()
    if device is None:
        print("Échec de la détection. Fin du programme.")
        return

    # --- ACQUISITION DU DARK ---
    print("\n========== ACQUISITION DU DARK ==========")
    input("Placez le bouchon opaque sur l'objectif, puis appuyez sur Entrée...")
    dark_mosaic = capture_average_mosaic(device, nodemap, tl_stream,
                                         num_images=N_IMAGES,
                                         gain_value=GAIN,
                                         exposure_value=EXPOSURE)
    dark_I0, dark_I45, dark_I90, dark_I135 = extract_channels(dark_mosaic)

    # Sauvegarde des canaux dark
    for name, data in [("I0", dark_I0), ("I45", dark_I45),
                       ("I90", dark_I90), ("I135", dark_I135)]:
        fname = os.path.join(base_dir, f"dark_{name}.mat")
        sio.savemat(fname, {f"dark_{name}": data})
        print(f"  Sauvegardé : {fname}")

    # Option : sauvegarde de la mosaïque dark complète
    sio.savemat(os.path.join(base_dir, f"dark_mosaic.mat"),
                {"dark_mosaic": dark_mosaic})

    # --- ACQUISITION DU FLAT ---
    print("\n========== ACQUISITION DU FLAT ==========")
    input("Placez la source uniforme non polarisée (écran+papier) et appuyez sur Entrée...")
    flat_mosaic = capture_average_mosaic(device, nodemap, tl_stream,
                                         num_images=N_IMAGES,
                                         gain_value=GAIN,
                                         exposure_value=EXPOSURE)
    flat_I0, flat_I45, flat_I90, flat_I135 = extract_channels(flat_mosaic)

    # --- CALCUL DES CARTES DE GAIN ---
    print("\n========== CALCUL DES CARTES DE CORRECTION ==========")
    dark_channels = [dark_I0, dark_I45, dark_I90, dark_I135]
    flat_channels = [flat_I0, flat_I45, flat_I90, flat_I135]
    channel_names = ["I0", "I45", "I90", "I135"]

    for dark, flat, name in zip(dark_channels, flat_channels, channel_names):
        # Flat corrigé du dark
        flat_ds = flat - dark
        # Protection contre les divisions par zéro
        flat_ds = np.where(flat_ds <= 0, 1e-6, flat_ds)
        mean_val = np.mean(flat_ds)
        gain = mean_val / flat_ds

        # Sauvegarde du gain
        fname = os.path.join(base_dir, f"gain_{name}.mat")
        sio.savemat(fname, {f"gain_{name}": gain})
        print(f"  Gain {name} sauvegardé : {fname}")

    print("\n========== CALIBRATION TERMINÉE ==========")
    print(f"Tous les fichiers sont dans : {base_dir}")
    print("Vous pouvez maintenant utiliser ces fichiers dans votre code de mesure.")

    # Fin
    print("Déconnexion de la caméra...")
    # device.disconnect() si nécessaire (selon l'API, le context manager le fait)


if __name__ == "__main__":
    main()