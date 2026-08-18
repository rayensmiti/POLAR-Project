import os
import sys
import time
import numpy as np
import cv2
from datetime import datetime
import scipy.io as sio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import colors
from io import BytesIO
from arena_api.system import system
from scipy.io import loadmat


#  DETECTION CAMERA LUCID 
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

    temperature_node = nodemap.get_node("DeviceTemperature")
    if temperature_node is not None:
        temperature_value = temperature_node.value
        print(f"Device actual temperature : {temperature_value:.4f} °C")

    return device, nodemap, tl_stream_nodemap


def compute_aopl_from_aopg(aopg_physical, cx, cy, fx, fy):
    """
    Calcule l'AoPL, l'azimut et l'élévation à partir de l'AoPG (pleine résolution).
    Retourne AOPL, azimuth_deg, elevation_deg.
    """
    AOPG = aopg_physical.astype(np.float32)
    h, v = AOPG.shape

    X = np.tile(np.arange(v), (h, 1))
    Y = np.tile(np.arange(h).reshape(h, 1), (1, v))

    # Coordonnées normalisées
    Xn = (X - cx) / fx
    Yn = (Y - cy) / fy

    # Azimut (degrés, 0‑360)
    azimuth_rad = np.arctan2(Yn, Xn)
    azimuth_deg = np.degrees(azimuth_rad) % 360

    # Élévation (degrés, 0° = horizon, 90° = zénith)
    r = np.sqrt(Xn**2 + Yn**2)
    elevation_deg = 90.0 - np.degrees(np.arctan(r))

    # Angle φ pour l'AoPL
    phi_deg = azimuth_deg % 180
    phi_deg = np.nan_to_num(phi_deg)

    AOPL = np.mod(AOPG - phi_deg, 180)
    return AOPL, azimuth_deg, elevation_deg


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
    cbar = plt.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=cmap_name),
        cax=ax,
        orientation='horizontal'
    )
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


def acquisition_lucid_complete(device, nodemap, tl_stream_nodemap, path_lucid, gain_value=0, exposure_value=200, t0_global=None):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs(path_lucid, exist_ok=True)

    print(f"Dossier Lucid : {path_lucid}")
    
    # --- Désactiver tous les automatismes ---
    exposure_auto_node = nodemap.get_node("ExposureAuto")
    if exposure_auto_node is not None:
        exposure_auto_node.value = "Off"

    gain_auto_node = nodemap.get_node("GainAuto")
    if gain_auto_node is not None:
        gain_auto_node.value = "Off"

    gain_node = nodemap.get_node("Gain")
    exposure_node = nodemap.get_node("ExposureTime")

    if gain_node:
        gain_node.value = float(gain_value)

    if exposure_node:
        exposure_node.value = float(exposure_value)

    tl_stream_nodemap['StreamAutoNegotiatePacketSize'].value = True
    tl_stream_nodemap['StreamPacketResendEnable'].value = True

    nodes = nodemap.get_node(['Width', 'Height', 'PixelFormat'])
    nodes['Width'].value = nodes['Width'].max
    nodes['Height'].value = nodes['Height'].max

    width = nodes['Width'].value
    height = nodes['Height'].value

    if t0_global is None:
        t0_global = time.time()

    # PHASE 1 : ACQUISITIONS RAPIDES EN RAM
   

    # AOPG
    nodes['PixelFormat'].value = 'PolarizedAolp_Mono8'
    with device.start_stream():
        image_buffer = device.get_buffer()
        print(f"[TIME] LUCID AoPG capturée à t = {time.time() - t0_global:.3f} s")

        aopg_data = np.ctypeslib.as_array(
            image_buffer.pdata,
            shape=(image_buffer.height, image_buffer.width)
        ).copy()

        aopg_physical = aopg_data.astype(np.float32) * (180.0 / 255.0)

        device.requeue_buffer(image_buffer)
        device.stop_stream()
    
    #  DOP 
    nodes['PixelFormat'].value = 'PolarizedDolp_Mono8'
    with device.start_stream():


        image_buffer= device.get_buffer()
        print(f"[TIME] LUCID DoP capturée à t = {time.time() - t0_global:.3f} s")

        dop_data = np.ctypeslib.as_array(
            image_buffer.pdata,
            shape=(image_buffer.height, image_buffer.width)
        ).copy()
        
        dop_physical = dop_data.astype(np.float32) / 255.0

        device.requeue_buffer(image_buffer)
        device.stop_stream()

    #  RAW 
    nodes['PixelFormat'].value = 'Mono12'
    with device.start_stream():
        image_buffer = device.get_buffer()
        print(f"[TIME] LUCID RAW capturée à t = {time.time() - t0_global:.3f} s")

        raw_bytes = bytes(image_buffer.data)
        image_16bit = np.frombuffer(raw_bytes, dtype=np.uint16).reshape((height, width)).copy()

        device.requeue_buffer(image_buffer)
        device.stop_stream()



    t_capture_done = time.time()
    print(f"[TIME] LUCID acquisitions brutes terminées à t = {t_capture_done - t0_global:.3f} s")

   
    # PHASE 2 : TRAITEMENT + SAUVEGARDE APRÈS CAPTURE
   

    print("[LUCID] Début sauvegardes et traitements...")

    #  RAW sauvegarde 
    image_8bit = (image_16bit / 16).astype(np.uint8)

    raw_png = os.path.join(path_lucid, f"Raw.png")
    raw_mat = os.path.join(path_lucid, f"Raw.mat")

    cv2.imwrite(raw_png, image_8bit)
    sio.savemat(raw_mat, {
        "ImageMono12": image_16bit,
        "Gain_dB": gain_value,
        "Exposure_us": exposure_value   
    })   

    # DOP sauvegarde 
    dop_mat = os.path.join(path_lucid, f"DOP.mat")
    dop_png = os.path.join(path_lucid, f"DOP.png")

    sio.savemat(dop_mat, {
        "DoP": dop_physical,
        "Gain_dB": gain_value,
        "Exposure_us": exposure_value
    })

    save_colormap_with_colorbar(
        dop_physical, "viridis", 0.0, 1.0,
        "Degree of Polarization - DoP", dop_png
    )

    #  AOPG sauvegarde 
    aopg_mat = os.path.join(path_lucid, f"AOPG.mat")
    aopg_png = os.path.join(path_lucid, f"AOPG.png")

    sio.savemat(aopg_mat, {
        "AOPG": aopg_physical,
        "Gain_dB": gain_value,
        "Exposure_us": exposure_value
    })


    save_colormap_with_colorbar(
        aopg_physical, "hsv", 0.0, 180.0,
        "Global Angle of Polarization - AoPG (°)", aopg_png
    )

    #  AOPL calcul + sauvegarde 
    # Calcul de l'AoPL, azimut et élévation
    AOPL, azimut, elevation = compute_aopl_from_aopg(aopg_physical, cx, cy, fx, fy)

    # Sauvegarde AoPL
    aopl_mat = os.path.join(path_lucid, f"aopl.mat")
    sio.savemat(aopl_mat, {"AOPL": AOPL})

    # Sauvegarde azimut
    azimut_mat = os.path.join(path_lucid, f"azimut.mat")
    sio.savemat(azimut_mat, {"azimut": azimut, "Gain_dB": gain_value, "Exposure_us": exposure_value})

    # Sauvegarde élévation
    elevation_mat = os.path.join(path_lucid, f"elevation.mat")
    sio.savemat(elevation_mat, {"elevation": elevation, "Gain_dB": gain_value, "Exposure_us": exposure_value})

    # Visualisation AoPL
    aopl_png = os.path.join(path_lucid, f"AOPL.png")
    save_colormap_with_colorbar(
        AOPL, "hsv", 0.0, 180.0,
        "Local Angle of Polarization - AoPL (°)", aopl_png
    )

    tf_global = time.time()

    print(f"[TIME] LUCID sauvegardes terminées à t = {tf_global - t0_global:.3f} s")
    print(f"[MAIN] Time of acquisition: {tf_global - t0_global:.3f} s")
    print(f"Lucid acquisition terminée. Sauvegarde dans : {path_lucid}")

def run_lucid_wait_signal(start_event, path_lucid, t0_shared):
    print("[LUCID] Initialisation caméra Lucid...")

    device_lucid, nodemap_lucid, tl_stream_nodemap_lucid = detect_lucid_camera()

    if device_lucid is None:
        print("[LUCID] Caméra LUCID non détectée.")
        return

    print("[LUCID] Caméra détectée. En attente du signal JAI...")

    start_event.wait()

    #time.sleep(0.5)

    t0_global=t0_shared.value

    print("[LUCID] Signal reçu. Acquisition LUCID démarrée.")

    acquisition_lucid_complete(
        device_lucid,
        nodemap_lucid,
        tl_stream_nodemap_lucid,
        path_lucid,
        t0_global=t0_global
    )

    print("[LUCID] Acquisition terminée.")

def capture_lucid_aopg_ram(device, nodemap, t0_global):
    nodes = nodemap.get_node(['PixelFormat'])
    nodes['PixelFormat'].value = 'PolarizedAolp_Mono8'

    with device.start_stream():
        image_buffer = device.get_buffer()
        print(f"[TIME] LUCID AoPG capturée à t = {time.time() - t0_global:.3f} s")

        aopg_data = np.ctypeslib.as_array(
            image_buffer.pdata,
            shape=(image_buffer.height, image_buffer.width)
        ).copy()

        aopg_physical = aopg_data.astype(np.float32) * (180.0 / 255.0)

        device.requeue_buffer(image_buffer)
        device.stop_stream()

    return aopg_physical


def capture_lucid_dop_ram(device, nodemap, t0_global):
    nodes = nodemap.get_node(['PixelFormat'])
    nodes['PixelFormat'].value = 'PolarizedDolp_Mono8'

    with device.start_stream():
        image_buffer = device.get_buffer()
        print(f"[TIME] LUCID DoP capturée à t = {time.time() - t0_global:.3f} s")

        dop_data = np.ctypeslib.as_array(
            image_buffer.pdata,
            shape=(image_buffer.height, image_buffer.width)
        ).copy()

        dop_physical = dop_data.astype(np.float32) / 255.0

        print("[DEBUG] DOP raw min/max:", dop_data.min(), dop_data.max())
        print("[DEBUG] DOP mean/std:", dop_physical.mean(), dop_physical.std())

        device.requeue_buffer(image_buffer)
        device.stop_stream()

    return dop_physical


def capture_lucid_raw_ram(device, nodemap, t0_global):
    nodes = nodemap.get_node(['Width', 'Height', 'PixelFormat'])
    width = nodes['Width'].value
    height = nodes['Height'].value

    nodes['PixelFormat'].value = 'Mono12'

    with device.start_stream():
        image_buffer = device.get_buffer()
        print(f"[TIME] LUCID RAW capturée à t = {time.time() - t0_global:.3f} s")

        raw_bytes = bytes(image_buffer.data)
        image_16bit = np.frombuffer(raw_bytes, dtype=np.uint16).reshape((height, width)).copy()

        device.requeue_buffer(image_buffer)
        device.stop_stream()

    return image_16bit

def save_lucid_results(path_lucid, timestamp, lucid_data, gain_value=0, exposure_value=150):
    os.makedirs(path_lucid, exist_ok=True)

    print("[LUCID] Début sauvegardes et traitements...")
    calib = loadmat('camera_python.mat')
    K = calib["K"]
    cx = K[2, 0]
    cy = K[2, 1]
    fx = K[0, 0]
    fy = K[1, 1]

    image_16bit = lucid_data.get("RAW")
    dop_physical = lucid_data.get("DOP")
    aopg_physical = lucid_data.get("AOPG")

    if image_16bit is not None:
        image_8bit = (image_16bit / 16).astype(np.uint8)

        raw_png = os.path.join(path_lucid, f"Raw.png")
        raw_mat = os.path.join(path_lucid, f"Raw.mat")

        cv2.imwrite(raw_png, image_8bit)
        sio.savemat(raw_mat, {
            "ImageMono12": image_16bit,
            "Gain_dB": gain_value,
            "Exposure_us": exposure_value
        })

    if dop_physical is not None:
        dop_mat = os.path.join(path_lucid, f"DOP.mat")
        dop_png = os.path.join(path_lucid, f"DOP.png")

        sio.savemat(dop_mat, {
            "DoP": dop_physical,
            "Gain_dB": gain_value,
            "Exposure_us": exposure_value
        })

        save_colormap_with_colorbar(
            dop_physical, "viridis", 0.0, 1.0,
            "Degree of Polarization - DoP", dop_png
        )

    if aopg_physical is not None:
        aopg_mat = os.path.join(path_lucid, f"AOPG.mat")
        aopg_png = os.path.join(path_lucid, f"AOPG.png")

        sio.savemat(aopg_mat, {
            "AOPG": aopg_physical,
            "Gain_dB": gain_value,
            "Exposure_us": exposure_value
        })

        save_colormap_with_colorbar(
            aopg_physical, "hsv", 0.0, 180.0,
            "Global Angle of Polarization - AoPG (°)", aopg_png
        )

        AOPL, azimuth, elevation = compute_aopl_from_aopg(aopg_physical, cx, cy, fx ,fy)

        aopl_mat = os.path.join(path_lucid, f"aopl.mat")
        aopl_png = os.path.join(path_lucid, f"AOPL.png")

        sio.savemat(aopl_mat, {
            "AOPL": AOPL,
            "Gain_dB": gain_value,
            "Exposure_us": exposure_value
        })

        save_colormap_with_colorbar(
            AOPL, "hsv", 0.0, 180.0,
            "Local Angle of Polarization - AoPL (°)", aopl_png
        )
        # Sauvegarde azimut
        azimuth_mat = os.path.join(path_lucid, f"azimut.mat")
        sio.savemat(azimuth_mat, {"azimut": azimuth, "Gain_dB": gain_value, "Exposure_us": exposure_value})

        # Sauvegarde élévation
        elevation_mat = os.path.join(path_lucid, f"elevation.mat")
        sio.savemat(elevation_mat, {"elevation": elevation, "Gain_dB": gain_value, "Exposure_us": exposure_value})
    print(f"[LUCID] Sauvegardes terminées dans : {path_lucid}")

def run_lucid_command_mode(command_queue, done_event, path_lucid, t0_shared, lucid_ready_event=None):

    print("[LUCID] Initialisation caméra Lucid...")
    device_lucid, nodemap_lucid, tl_stream_nodemap_lucid = detect_lucid_camera()

    if device_lucid is None:
        print("[LUCID] Caméra non détectée.")
        if lucid_ready_event:
            lucid_ready_event.set()  # débloquer JAI même en cas d'erreur
        return

    os.makedirs(path_lucid, exist_ok=True)

    gain_value = 0
    exposure_value = 150
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    gain_node = nodemap_lucid.get_node("Gain")
    if gain_node:
        gain_node.value = float(gain_value)

    tl_stream_nodemap_lucid['StreamAutoNegotiatePacketSize'].value = True
    tl_stream_nodemap_lucid['StreamPacketResendEnable'].value = True

    nodes = nodemap_lucid.get_node(['Width', 'Height'])
    nodes['Width'].value = nodes['Width'].max
    nodes['Height'].value = nodes['Height'].max

    # LUCID est prête — JAI peut démarrer
    print("[LUCID] Caméra prête. Signal envoyé à JAI.")
    if lucid_ready_event:
        lucid_ready_event.set()

    lucid_data = {}

    while True:
        cmd = command_queue.get()

        if cmd == "STOP":
            print("[LUCID] STOP reçu.")
            break

        t0_global = t0_shared.value
        print(f"[LUCID] Commande reçue : {cmd}")

        if cmd == "AOPG":
            lucid_data["AOPG"] = capture_lucid_aopg_ram(
                device_lucid, nodemap_lucid, t0_global
            )
            done_event.set()
        elif cmd == "DOP":
            lucid_data["DOP"] = capture_lucid_dop_ram(
                device_lucid, nodemap_lucid, t0_global
            )
            done_event.set()
        elif cmd == "RAW":
            lucid_data["RAW"] = capture_lucid_raw_ram(
                device_lucid, nodemap_lucid, t0_global
            )
            done_event.set()
            # Signal : toutes les captures sont terminées
            print("[LUCID] Toutes captures terminées.")
            

    save_lucid_results(
        path_lucid, timestamp, lucid_data, gain_value, exposure_value
    )
    print("[LUCID] Process Lucid terminé.")

# MAIN

if __name__ == "__main__":
    device_lucid, nodemap_lucid, tl_stream_nodemap_lucid = detect_lucid_camera()

    if device_lucid is None:
        print("Caméra LUCID non détectée.")
        exit()
    else:
        print("Caméra LUCID détectée et prête.")

    now = datetime.now()
    session_name = now.strftime("%d.%m.%Y_%Hh%Mm%Ss")

    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path_lucid = os.path.join(base_path, "Data", "LUCID", session_name)
    # Chargement des paramètres calibrés (MATLAB -> Python)
    calib = loadmat('camera_python.mat')
    K = calib["K"]                    # forme MATLAB : [fx 0 0; 0 fy 0; cx cy 1]
    cx = K[2, 0]                      # centre optique x
    cy = K[2, 1]                      # centre optique y
    fx = K[0, 0]                      # focale x
    fy = K[1, 1]                      # focale y

    radial = calib["radial"].ravel()
    tangent = calib["tangent"].ravel()
    distCoeffs = np.array([radial[0], radial[1], tangent[0], tangent[1], 0.0])  # pour plus tard si besoin    

    t0_global = time.time()
    acquisition_lucid_complete(
        device_lucid,
        nodemap_lucid,
        tl_stream_nodemap_lucid,
        path_lucid,
        t0_global=t0_global,
    )
   
    print("Acquisition terminée")