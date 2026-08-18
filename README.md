# POLAR-Project
Synchronization of acquisition of 2 cameras (UV JAI + Visible Lucid) for sun position estimation using polarimetry. Includes acquisition, synchronization via multiprocessing and comparison of sun estimation methods.

## Overview

The project aims to estimate the sun's azimuth using polarimetric measurements from two synchronized cameras:
- **JAI GOX-8105M-PGE** (UV, with rotating polarizer)
- **Lucid TRI050S1-P** (Visible, Sony Polarsens™ sensor)

The system includes:
- **Acquisition** – Python scripts for synchronized capture of polarimetric images.
- **Calibration** – Radiometric, geometric and polarimetric calibration of the Lucid camera.
- **Estimation** – MATLAB scripts implementing **Eigenvalue** and **Hough transform** methods.

##  Repository Structure
```text
POLAR-Project/
│
├── README.md
├── requirements.txt
│
├── arena_api-2.8.4-py3-none-any.whl # Lucid Arena SDK wheel
├── eBUS_Python_JAI_Raspberry_Pi4_Pi5_...zip # JAI eBUS Python bindings
├── eBUS_SDK_JAI_Raspberry_Pi4_Pi5_...zip # JAI eBUS SDK
├── VNC-Server-7.16.0-Linux-ARM64.deb # VNC server for remote access
│
├── Acquisition/
│ ├── GRAPHIQUE_SYNCHRO_MULTI.py # Multi‑session acquisition (legacy)
│ ├── GRAPHIQUE_SYNCHRO_POLARIZE.py # Main synchronized acquisition script
│ ├── JAI_ONLY.py # Unified JAI acquisition
│ ├── LUCID_ONLY.py # Lucid 3‑format acquisition
│ └── POLARIZED_LUCID.py # Lucid PolarizeMono12 + radiometric calibration
│
├── Calibration Lucid/
│ ├── cameraParams.mat # Geometric calibration parameters
│ ├── camera_python.mat # Geometric calibration (Python format)
│ ├── RADIOMETRIC_CHANNEL_CAL_LUCID.py # Radiometric calibration script
│ ├── Dark_moy/ # Dark master files (4 channels)
│ │ ├── dark_I0.mat
│ │ ├── dark_I45.mat
│ │ ├── dark_I90.mat
│ │ ├── dark_I135.mat
│ │ └── dark_mosaic.mat
│ └── Flat_gain/ # Gain master files (4 channels)
│ ├── gain_I0.mat
│ ├── gain_I45.mat
│ ├── gain_I90.mat
│ ├── gain_I135.mat
│ └── flat_mosaic.mat
│
└── Estimation solaire/
├── AZIMUT_JAI_LUCID.m # Compare JAI vs Lucid (Eigen) with statistics
├── detect_sun_line_hough.m # Hough transform estimation
├── ESTIMATION_az_eig.m # Eigenvalue estimation (single session)
├── ESTIMATION_hough.m # Hough estimation (single session)
├── hough_vs_eigen_with_errors.m # Compare Hough vs Eigen on multiple sessions
└── Sun_Estimator_az_eig2.m # Core Eigenvalue estimation function
```

## Installation (Raspberry Pi 4/5, Ubuntu 22.04)
### 0. Prepare the SD card (Ubuntu 22.04)

To install Ubuntu 22.04 on your Raspberry Pi:

#### 1. Download Raspberry Pi Imager
- Go to: https://www.raspberrypi.com/software/
- Download and install **Raspberry Pi Imager** on your PC (Windows/Mac/Linux)

#### 2. Launch Raspberry Pi Imager
- Insert your SD card into your PC
- Open Raspberry Pi Imager

#### 3. Choose the OS
- Click on **"Choose OS"**
- Scroll down and select **"Other general-purpose OS"**
- Select **"Ubuntu"**
- Select **"Ubuntu 22.04 LTS (64-bit)"** (or the latest 64-bit version)

#### 4. Choose the SD card
- Click on **"Choose Storage"**
- Select your SD card from the list (be careful to select the correct one)

#### 5. Write the image
- Click **"Write"**
- Confirm the warning (all data on the SD card will be erased)
- Wait for the writing and verification to complete

#### 6. Insert the SD card
- Remove the SD card from your PC
- Insert it into your Raspberry Pi

###  System update

```bash
sudo apt update && sudo apt upgrade -y

###  Install system dependencies

```bash
sudo apt install -y python3-pip python3-tk python3-dev build-essential
```

###  Install Python packages

```bash
pip install -r requirements.txt
```
This project was developed and tested with **Python 3.10.12**.

###  Install camera SDKs

####  JAI eBUS SDK

1. Unzip the SDK:
   ```bash
   unzip eBUS_SDK_JAI_Raspberry_Pi4_Pi5_linux-aarch64-arm-6.5.1-6797.zip
   ```
2. Follow the installer instructions (typically `sudo ./install.sh`).
3. Install the Python bindings:
   ```bash
   unzip eBUS_Python_JAI_Raspberry_Pi4_Pi5_linux-aarch64-arm-6.5.1-6797.zip
   cd eBUS_Python_JAI_Raspberry_Pi4_Pi5_linux-aarch64-arm-6.5.1-6797
   sudo python3 setup.py install
   ```

####  Lucid Arena SDK

```bash
pip install arena_api-2.8.4-py3-none-any.whl
```

###  Network configuration (static IP)

To ensure stable communication with the cameras, set a static IP on the Raspberry Pi.

Edit the netplan configuration:
```bash
sudo nano /etc/netplan/01-netcfg.yaml
```

Add the following (adjust to your network):
```yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: no
      addresses:
        - 169.254.100.1/24
      gateway4: 169.254.100.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
```

Apply the changes:
```bash
sudo netplan apply
```

### Remote access (VNC) – Headless mode

To control the Raspberry Pi remotely without a monitor, you can set up a **virtual display** and connect via VNC.

#### 1. Install VNC Server

```bash
sudo dpkg -i VNC-Server-7.16.0-Linux-ARM64.deb
sudo systemctl enable vncserver
sudo systemctl start vncserver
```

#### 2. Install the virtual display driver

```bash
sudo apt install xserver-xorg-video-dummy
```

#### 3. Create the configuration file

```bash
sudo mkdir -p /etc/X11/xorg.conf.d/
sudo nano /etc/X11/xorg.conf.d/10-dummy.conf
```

#### 4. Add the following configuration

Paste this into the file:

```
Section "Device"
    Identifier  "DummyDevice"
    Driver      "dummy"
    VideoRam    256000
EndSection

Section "Monitor"
    Identifier "DummyMonitor"
    HorizSync 31.5-48.5
    VertRefresh 50-70
EndSection

Section "Screen"
    Identifier "DummyScreen"
    Device "DummyDevice"
    Monitor "DummyMonitor"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Modes "1920x1080"
    EndSubSection
EndSection
```

Save and exit (`Ctrl+X`, then `Y`, then `Enter`).

#### 5. Reboot the Raspberry Pi

```bash
sudo reboot
```
#### 6. Connect from your PC

- Install **RealVNC Viewer** on your PC (Windows/Mac/Linux)
- Open RealVNC Viewer
- Enter the Raspberry Pi's IP address (e.g., `169.254.100.1`)
- Enter your Pi username and password

You should now see the Raspberry Pi desktop remotely, without needing an HDMI cable.

##  Performance optimization (Raspberry Pi 4)

The acquisition of two GigE Vision cameras can cause packet losses (`TOO_MANY_CONSECUTIVE_RESENDS`). The following optimizations significantly reduce this issue.

### 1. CPU governor – performance mode

```bash
sudo cpufreq-set -g performance
```

To make it permanent:
```bash
sudo nano /etc/default/cpufrequtils
```
Add:
```
GOVERNOR="performance"
```


### 2. Run with core isolation

```bash
taskset -c 2,3 python3 Acquisition/GRAPHIQUE_SYNCHRO_POLARIZE.py
```

### 3. Disable unnecessary services

```bash
sudo systemctl disable bluetooth
sudo systemctl disable wpa_supplicant
```

---

##  Usage

###  Multi‑session acquisition (legacy)

```bash
cd Acquisition/
python3 GRAPHIQUE_SYNCHRO_MULTI.py
```

This script captures **3 formats from Lucid** (DoP, AoPG, RAW) using threading/multiprocessing.  
**Note:** This version does **not** apply radiometric corrections. It is kept for reference.

###  Synchronized acquisition (recommended)

```bash
cd Acquisition/
python3 GRAPHIQUE_SYNCHRO_POLARIZE.py
```

You will be prompted to enter:
- **Latitude** and **Longitude**
- **Total duration** (minutes)
- **Time interval** between acquisitions

The script:
- Creates two folders: `Data/JAI/<timestamp>/` and `Data/LUCID/<timestamp>/`
- Acquires 4 polarimetric images from JAI (0°,45°,90°,135°)
- Acquires a single PolarizeMono12 image from Lucid (extracts 4 channels)
- Applies radiometric corrections (dark/gain) to Lucid data
- Saves ephemeris data (sun azimuth / elevation)

**Generated data:**

| Camera | Files generated | Description |
| :--- | :--- | :--- |
| **JAI** | `I_0.tiff`, `I_45.tiff`, `I_90.tiff`, `I_135.tiff` | 4 raw polarimetric images (Mono8) |
| | `dop.npy`, `aop.npy` | Degree of Polarization (DoP) and Angle of Polarization (AoP) |
| | `aopl.mat`, `azimut.mat`, `elevation.mat` | Local AoP, azimuth and elevation matrices |
| **LUCID** | `mosaic_*.mat` | Raw PolarizeMono12 mosaic |
| | `I0.mat`, `I45.mat`, `I90.mat`, `I135.mat` | Corrected channels (dark/gain applied) |
| | `DoP.mat`, `AoPG.mat`, `AoPL.mat` | Degree of Polarization, Global AoP, Local AoP |
| | `azimut.mat`, `elevation.mat` | Azimuth and elevation matrices |
| **Both** | `ephemeride.json` | Sun azimuth and elevation (calculated from latitude, longitude and UTC time) |

### Lucid acquisition – two versions

| Script | Description | Generated data | Use case |
| :--- | :--- | :--- | :--- |
| `LUCID_ONLY.py` | Captures 3 formats (DoP, AoPG, RAW) | `DoP.mat`, `AoPG.mat`, `RAW.mat` | Quick acquisition, no radiometric correction |
| `POLARIZED_LUCID.py` | Captures PolarizeMono12 + applies dark/gain | `mosaic_*.mat`, `I0.mat`, `I45.mat`, `I90.mat`, `I135.mat`, `DoP.mat`, `AoPG.mat`, `AoPL.mat`, `azimut.mat`, `elevation.mat` | High‑precision acquisition (recommended) |

The main script `GRAPHIQUE_SYNCHRO_POLARIZE.py` uses `POLARIZED_LUCID.py` by default.

###  JAI acquisition (standalone)

```bash
cd Acquisition/
python3 JAI_ONLY.py
```

This captures 4 images (0°,45°,90°,135°) and saves them as TIFF files.

**Generated data:**

| File | Description |
| :--- | :--- |
| `I_0.tiff`, `I_45.tiff`, `I_90.tiff`, `I_135.tiff` | 4 raw polarimetric images (Mono8) |
| `dop.npy` | Degree of Polarization (DoP) |
| `aop.npy` | Global Angle of Polarization (AoP) |
| `aopl.mat` | Local Angle of Polarization (AoPL) |
---

##  Post‑processing (MATLAB)

### 1. Compare JAI vs Lucid (Eigenvalue method)

```matlab
% In MATLAB, navigate to "Estimation solaire/"
run AZIMUT_JAI_LUCID.m
```
- Select the parent folder containing JAI sessions.
- Select the parent folder containing Lucid sessions.
- The script computes azimuth estimates, plots time series, generates boxplots, and performs **statistical tests** (Mann‑Whitney, Student, or Welch depending on sample size and normality).

### 2. Compare Hough vs Eigenvalue (single camera)

```matlab
run hough_vs_eigen_with_errors.m
```
- Select a parent folder with multiple sessions.
- Compares the two methods and displays MAE, RMSE, Biais, and boxplots.

### 3. Single‑session estimation

| Script | Method |
| :--- | :--- |
| `ESTIMATION_az_eig.m` | Eigenvalue (single session) |
| `ESTIMATION_hough.m` | Hough transform (single session) |

---

##  Statistical tests (JAI vs Lucid)

The script `AZIMUT_JAI_LUCID.m` automatically applies:

| Condition | Test used |
| :--- | :--- |
| `n < 7` | **Mann‑Whitney** (non‑parametric) |
| `n ≥ 7` + normal + equal variances | **Student's t‑test** |
| `n ≥ 7` + normal + unequal variances | **Welch's t‑test** |
| `n ≥ 7` + non‑normal | **Mann‑Whitney** |

Results are displayed in the MATLAB console with:
- p‑value
- Conclusion (significant / not significant)
- Which camera is better (if significant)



##  References

- [eBUS SDK – JAI](https://www.jai.com/products/ebus-sdk)
- [Arena SDK – Lucid](https://www.thinklucid.com/arena-sdk/)
- [Pysolar – Solar ephemeris](https://pysolar.readthedocs.io/)
- [Meteociel – Weather data](https://www.meteociel.fr)

## Author

**Rayen SMITI**  
Internship Project – PFE  
Institut des Sciences du Mouvement – UMR7287  
2026
