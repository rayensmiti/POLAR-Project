import os
import numpy as np
import cv2
from datetime import datetime, timezone
import scipy.io as sio
import matplotlib.pyplot as plt
from matplotlib import colors
from io import BytesIO
from scipy.io import loadmat
import json
from pysolar.solar import get_altitude, get_azimuth

# ------------------------------------------------------------
# Éphéméride solaire
# ------------------------------------------------------------
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


# ------------------------------------------------------------
# Détection caméra Lucid
# ------------------------------------------------------------
def detect_lucid_camera():
    from arena_api.system import system
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
    return device, nodemap, tl_stream_nodemap


# ------------------------------------------------------------
# Calcul de l’AoPL (version actuelle, retourne uniquement AoPL)
# ------------------------------------------------------------
def compute_aopl_from_aopg(aopg_physical, cx, cy, fx, fy):
    AOPG = aopg_physical.astype(np.float32)
    h, v = AOPG.shape
    X_half = np.tile(np.arange(v), (h, 1))
    Y_half = np.tile(np.arange(h).reshape(h, 1), (1, v))
    X_full = 2 * X_half + 1
    Y_full = 2 * Y_half + 1
    Xc = (X_full - cx) / fx
    Yc = (Y_full - cy) / fy
    phi = np.degrees(np.arctan2(Yc, Xc))
    phi = np.mod(phi, 180)
    phi = np.nan_to_num(phi)
    AOPL = np.mod(AOPG - phi, 180)
    return AOPL


# ------------------------------------------------------------
# Visualisation avec colorbar
# ------------------------------------------------------------
def save_colormap_with_colorbar(image_data, cmap_name, vmin, vmax, label, save_path):
    if cmap_name == "viridis":
        image_uint8 = cv2.normalize(image_data, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        cm_nparray = cv2.applyColorMap(image_uint8, cv2.COLORMAP_VIRIDIS)
    elif cmap_name == "hsv":
        image_uint8 = ((image_data / vmax) * 255).astype(np.uint8)
        cm_nparray = cv2.applyColorMap(image_uint8, cv2.COLORMAP_HSV)
    else:
        raise ValueError("Colormap non supportée")
    fig, ax = plt.subplots(figsize=(5, 0.5))
    fig.subplots_adjust(bottom=0.5)
    norm = colors.Normalize(vmin=vmin, vmax=vmax)
    cbar = plt.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap_name),
                        cax=ax, orientation='horizontal')
    cbar.set_label(label)
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0.1)
    plt.close(fig)
    buf.seek(0)
    colorbar_img = np.frombuffer(buf.getvalue(), dtype=np.uint8)
    colorbar_img = cv2.imdecode(colorbar_img, cv2.IMREAD_COLOR)
    bar_height = 250
    colorbar_img = cv2.resize(colorbar_img, (cm_nparray.shape[1], bar_height))
    colorbar_img = colorbar_img.astype(cm_nparray.dtype)
    combined_img = cv2.vconcat([cm_nparray, colorbar_img])
    cv2.imwrite(save_path, combined_img)


# ------------------------------------------------------------
# Acquisition rapide (sauvegarde brute uniquement)
# ------------------------------------------------------------
def acquisition_lucid_rapide(device, nodemap, tl_stream_nodemap, path_lucid,
                             gain_value=0, exposure_value=150):
    exposure_auto_node = nodemap.get_node("ExposureAuto")
    if exposure_auto_node: exposure_auto_node.value = "Off"
    gain_auto_node = nodemap.get_node("GainAuto")
    if gain_auto_node: gain_auto_node.value = "Off"
    gain_node = nodemap.get_node("Gain")
    if gain_node: gain_node.value = float(gain_value)
    expo_node = nodemap.get_node("ExposureTime")
    if expo_node: expo_node.value = float(exposure_value)
    tl_stream_nodemap['StreamAutoNegotiatePacketSize'].value = True
    tl_stream_nodemap['StreamPacketResendEnable'].value = True
    nodes = nodemap.get_node(['Width', 'Height', 'PixelFormat'])
    nodes['Width'].value = nodes['Width'].max
    nodes['Height'].value = nodes['Height'].max
    nodes['PixelFormat'].value = 'PolarizeMono12'
    width = nodes['Width'].value
    height = nodes['Height'].value

    print("[LUCID] Capture rapide PolarizeMono12...")
    with device.start_stream():
        image_buffer = device.get_buffer()
        acquisition_time_utc = datetime.now(timezone.utc)
        raw_bytes = bytes(image_buffer.data)
        mosaic_16bit = np.frombuffer(raw_bytes, dtype=np.uint16).reshape((height, width)).copy()
        device.requeue_buffer(image_buffer)
        device.stop_stream()

    os.makedirs(path_lucid, exist_ok=True)
    timestamp = acquisition_time_utc.strftime('%Y%m%d_%H%M%S')
    sio.savemat(os.path.join(path_lucid, f"mosaic_{timestamp}.mat"),
                {"MosaicPolarized": mosaic_16bit})
    print(f"[LUCID] Capture rapide terminée. Mosaïque sauvegardée dans {path_lucid}")


# ------------------------------------------------------------
# Traitement différé d'une mosaïque sauvegardée
# ------------------------------------------------------------
def traiter_mosaic_lucid(path_lucid):
    import glob
    mosaic_files = sorted(glob.glob(os.path.join(path_lucid, "mosaic_*.mat")))
    if not mosaic_files:
        print("[LUCID] Aucun fichier mosaic trouvé dans", path_lucid)
        return
    mosaic_file = mosaic_files[-1]
    print(f"[LUCID] Traitement du fichier : {mosaic_file}")
    data = sio.loadmat(mosaic_file)
    mosaic_16bit = data['MosaicPolarized']

    # Paramètres de calibration géométrique
    #calib = loadmat('camera_python.mat')
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)  
    calib_path = os.path.join(parent_dir, 'camera_python.mat')
    calib = loadmat(calib_path)

    K = calib['K']
    cx, cy = K[2, 0], K[2, 1]
    fx, fy = K[0, 0], K[1, 1]

    # ----- Charger les masters dark et gains (AJOUTÉ) -----
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ou utilisez le chemin absolu
    dark_dir = os.path.join(base, "Data", "LUCID", "Dark_moy")          # vérifiez le nom exact (Dark-moy ?)
    gain_dir = os.path.join(base, "Data", "LUCID", "Flat_gain")

    dark_I0   = sio.loadmat(os.path.join(dark_dir, "dark_I0.mat"))["dark_I0"]
    dark_I45  = sio.loadmat(os.path.join(dark_dir, "dark_I45.mat"))["dark_I45"]
    dark_I90  = sio.loadmat(os.path.join(dark_dir, "dark_I90.mat"))["dark_I90"]
    dark_I135 = sio.loadmat(os.path.join(dark_dir, "dark_I135.mat"))["dark_I135"]

    gain_I0   = sio.loadmat(os.path.join(gain_dir, "gain_I0.mat"))["gain_I0"]
    gain_I45  = sio.loadmat(os.path.join(gain_dir, "gain_I45.mat"))["gain_I45"]
    gain_I90  = sio.loadmat(os.path.join(gain_dir, "gain_I90.mat"))["gain_I90"]
    gain_I135 = sio.loadmat(os.path.join(gain_dir, "gain_I135.mat"))["gain_I135"]

    # ----- Extraction des canaux bruts -----
    I0_raw   = mosaic_16bit[1::2, 1::2].astype(np.float64)
    I45_raw  = mosaic_16bit[0::2, 1::2].astype(np.float64)
    I90_raw  = mosaic_16bit[0::2, 0::2].astype(np.float64)
    I135_raw = mosaic_16bit[1::2, 0::2].astype(np.float64)

    # ----- Correction radiométrique -----
    I0   = np.clip((I0_raw   - dark_I0)   * gain_I0,   0, None)
    I45  = np.clip((I45_raw  - dark_I45)  * gain_I45,  0, None)
    I90  = np.clip((I90_raw  - dark_I90)  * gain_I90,  0, None)
    I135 = np.clip((I135_raw - dark_I135) * gain_I135, 0, None)

    # ----- Calcul Stokes & polarisation sur les canaux corrigés -----
    S0 = (I0 + I45 + I90 + I135) / 2.0
    S1 = I0 - I90
    S2 = I45 - I135
    with np.errstate(divide='ignore', invalid='ignore'):
        dop = np.abs(S1 + 1j * S2) / S0
        dop = np.nan_to_num(dop, nan=0.0, posinf=0.0, neginf=0.0)
    aopg_deg = np.mod(np.degrees(0.5 * np.arctan2(S2, S1)), 180.0)
    aopl_deg = compute_aopl_from_aopg(aopg_deg, cx, cy, fx, fy)

    # --- Calcul de l'azimut et de l'élévation (comme pour la JAI) ---
    # On utilise les mêmes formules que dans compute_aopl_from_aopg
    h, w = aopl_deg.shape
    X_half = np.tile(np.arange(w), (h, 1))
    Y_half = np.tile(np.arange(h).reshape(h, 1), (1, w))
    X_full = 2 * X_half + 1
    Y_full = 2 * Y_half + 1
    Xn = (X_full - cx) / fx
    Yn = (Y_full - cy) / fy

    azimuth_rad = np.arctan2(Yn, Xn)
    azimuth_deg = np.degrees(azimuth_rad) % 360

    r = np.sqrt(Xn**2 + Yn**2)
    elevation_deg = 90.0 - np.degrees(np.arctan(r))

    # --- Sauvegardes avec noms fixes (compatibles JAI) ---
    sio.savemat(os.path.join(path_lucid, "aopl.mat"), {"AoPL": aopl_deg})
    sio.savemat(os.path.join(path_lucid, "azimut.mat"), {"azimut": azimuth_deg})
    sio.savemat(os.path.join(path_lucid, "elevation.mat"), {"elevation": elevation_deg})

    # --- Visualisations (on garde l'horodatage pour les images, mais on peut aussi utiliser des noms fixes) ---
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    save_colormap_with_colorbar(dop, "viridis", 0.0, 1.0,
                                "Degree of Polarization - DoP",
                                os.path.join(path_lucid, f"DOP.png"))
    save_colormap_with_colorbar(aopg_deg, "hsv", 0.0, 180.0,
                                "Global Angle of Polarization - AoPG (°)",
                                os.path.join(path_lucid, f"AOPG.png"))
    save_colormap_with_colorbar(aopl_deg, "hsv", 0.0, 180.0,
                                "Local Angle of Polarization - AoPL (°)",
                                os.path.join(path_lucid, f"AOPL.png"))

    print(f"[LUCID] Traitement terminé. Résultats dans {path_lucid}")


# ------------------------------------------------------------
# Acquisition polarimétrique COMPLÈTE avec correction dark+flat
# ------------------------------------------------------------
def acquisition_polarimetrique_lucid(device, nodemap, tl_stream_nodemap,
                                     gain_value=0, exposure_value=150,
                                     latitude_deg=43.2317, longitude_deg=5.4396):
    # Chargement des paramètres de calibration géométrique
    calib = loadmat('camera_python.mat')
    K = calib['K']
    cx, cy = K[2, 0], K[2, 1]
    fx, fy = K[0, 0], K[1, 1]

    # Désactiver les automatismes
    exposure_auto_node = nodemap.get_node("ExposureAuto")
    if exposure_auto_node: exposure_auto_node.value = "Off"
    gain_auto_node = nodemap.get_node("GainAuto")
    if gain_auto_node: gain_auto_node.value = "Off"
    gain_node = nodemap.get_node("Gain")
    if gain_node: gain_node.value = float(gain_value)
    expo_node = nodemap.get_node("ExposureTime")
    if expo_node: expo_node.value = float(exposure_value)
    tl_stream_nodemap['StreamAutoNegotiatePacketSize'].value = True
    tl_stream_nodemap['StreamPacketResendEnable'].value = True

    nodes = nodemap.get_node(['Width', 'Height', 'PixelFormat'])
    nodes['Width'].value = nodes['Width'].max
    nodes['Height'].value = nodes['Height'].max
    nodes['PixelFormat'].value = 'PolarizeMono12'
    width = nodes['Width'].value
    height = nodes['Height'].value

    print("[LUCID] Capture PolarizeMono12...")
    with device.start_stream():
        image_buffer = device.get_buffer()
        acquisition_time_utc = datetime.now(timezone.utc)
        acquisition_time_local = datetime.now()
        raw_bytes = bytes(image_buffer.data)
        mosaic_16bit = np.frombuffer(raw_bytes, dtype=np.uint16).reshape((height, width)).copy()
        device.requeue_buffer(image_buffer)
        device.stop_stream()

    # Création du dossier de sauvegarde
    session_name = acquisition_time_local.strftime("%d.%m.%Y_%Hh%Mm%Ss")
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path_lucid = os.path.join(base, "Data", "LUCID", session_name)
    os.makedirs(path_lucid, exist_ok=True)
    print(f"[LUCID] Dossier de sauvegarde : {path_lucid}")

    timestamp = acquisition_time_utc.strftime('%Y%m%d_%H%M%S')

    # Sauvegarde éphéméride
    az, el = compute_solar_ephemeris(latitude_deg, longitude_deg, acquisition_time_utc)
    save_ephemeris_json(path_lucid, acquisition_time_utc, latitude_deg, longitude_deg, az, el)

    # Sauvegarde de la mosaïque brute
    sio.savemat(os.path.join(path_lucid, f"mosaic.mat"),
                {"MosaicPolarized": mosaic_16bit})
    mosaic_8bit = (mosaic_16bit / 16).astype(np.uint8)
    cv2.imwrite(os.path.join(path_lucid, f"mosaic.png"), mosaic_8bit)

    # ================================================================
    # CHARGEMENT DES MASTERS DARK ET GAINS (AJOUTÉ)
    # ================================================================
    dark_dir = os.path.join(base, "Data", "LUCID", "Dark_moy")
    gain_dir = os.path.join(base, "Data", "LUCID", "Flat_gain")

    dark_I0   = sio.loadmat(os.path.join(dark_dir, "dark_I0.mat"))["dark_I0"]
    dark_I45  = sio.loadmat(os.path.join(dark_dir, "dark_I45.mat"))["dark_I45"]
    dark_I90  = sio.loadmat(os.path.join(dark_dir, "dark_I90.mat"))["dark_I90"]
    dark_I135 = sio.loadmat(os.path.join(dark_dir, "dark_I135.mat"))["dark_I135"]

    gain_I0   = sio.loadmat(os.path.join(gain_dir, "gain_I0.mat"))["gain_I0"]
    gain_I45  = sio.loadmat(os.path.join(gain_dir, "gain_I45.mat"))["gain_I45"]
    gain_I90  = sio.loadmat(os.path.join(gain_dir, "gain_I90.mat"))["gain_I90"]
    gain_I135 = sio.loadmat(os.path.join(gain_dir, "gain_I135.mat"))["gain_I135"]

    # ================================================================
    # Extraction des canaux bruts
    # ================================================================
    I0_raw   = mosaic_16bit[1::2, 1::2].astype(np.float64)
    I45_raw  = mosaic_16bit[0::2, 1::2].astype(np.float64)
    I90_raw  = mosaic_16bit[0::2, 0::2].astype(np.float64)
    I135_raw = mosaic_16bit[1::2, 0::2].astype(np.float64)

    # ================================================================
    # CORRECTION RADIOMÉTRIQUE (AJOUTÉ)
    # ================================================================
    I0   = np.clip((I0_raw   - dark_I0)   * gain_I0,   0, None)
    I45  = np.clip((I45_raw  - dark_I45)  * gain_I45,  0, None)
    I90  = np.clip((I90_raw  - dark_I90)  * gain_I90,  0, None)
    I135 = np.clip((I135_raw - dark_I135) * gain_I135, 0, None)

    # Sauvegarde des canaux corrigés
    for name, img in [("I0", I0), ("I45", I45), ("I90", I90), ("I135", I135)]:
        sio.savemat(os.path.join(path_lucid, f"{name}.mat"), {name: img})
    # ================================================================
    # Calcul Stokes sur les canaux corrigés
    # ================================================================
    S0 = (I0 + I45 + I90 + I135) / 2.0
    S1 = I0 - I90
    S2 = I45 - I135
    with np.errstate(divide='ignore', invalid='ignore'):
        dop = np.abs(S1 + 1j * S2) / S0
        dop = np.nan_to_num(dop, nan=0.0, posinf=0.0, neginf=0.0)
    aopg_deg = np.mod(np.degrees(0.5 * np.arctan2(S2, S1)), 180.0)
    aopl_deg = compute_aopl_from_aopg(aopg_deg, cx, cy, fx, fy)

    # Sauvegarde DoP, AoPG, AoPL
    sio.savemat(os.path.join(path_lucid, f"dop.mat"), {"DoP": dop})
    sio.savemat(os.path.join(path_lucid, f"aopg.mat"), {"AoPG": aopg_deg})
    sio.savemat(os.path.join(path_lucid, f"aopl.mat"), {"AoPL": aopl_deg})

    # Visualisations
    save_colormap_with_colorbar(dop, "viridis", 0.0, 1.0,
                                "Degree of Polarization - DoP",
                                os.path.join(path_lucid, f"DOP.png"))
    save_colormap_with_colorbar(aopg_deg, "hsv", 0.0, 180.0,
                                "Global Angle of Polarization - AoPG (°)",
                                os.path.join(path_lucid, f"AOPG.png"))
    save_colormap_with_colorbar(aopl_deg, "hsv", 0.0, 180.0,
                                "Local Angle of Polarization - AoPL (°)",
                                os.path.join(path_lucid, f"AOPL.png"))

    print(f"[LUCID] Traitement terminé. Résultats dans {path_lucid}")


# ------------------------------------------------------------
# Point d'entrée (test standalone)
# ------------------------------------------------------------
if __name__ == "__main__":
    device, nodemap, tl_stream = detect_lucid_camera()
    if device is None:
        print("Caméra Lucid non détectée. Fin.")
        exit()

    # Chargement des paramètres de calibration (utilisé aussi dans le main)
    calib = loadmat('camera_python.mat')
    K = calib["K"]
    cx, cy = K[2, 0], K[2, 1]
    fx, fy = K[0, 0], K[1, 1]

    acquisition_polarimetrique_lucid(device, nodemap, tl_stream,
                                     gain_value=0, exposure_value=150,
                                     latitude_deg=43.2317, longitude_deg=5.4396)
    print("Acquisition polarimétrique terminée.")