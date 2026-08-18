# PvSampleUtils.py – version Python basée sur PvSampleUtils.h
import time
import threading
import sys
import select
import tty
import termios
import socket

gStop = False

def PvSleepMs(milliseconds):
    """Pause en millisecondes"""
    time.sleep(milliseconds / 1000.0)

def PvWaitForKeyPress():
    """Attend un appui clavier (non-bloquant sur Linux)"""
    print("Appuie sur une touche pour continuer...")
    input()

def PvKbHit():
    """Vérifie s'il y a une touche pressée (Linux)"""
    if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
        return True
    return False

def PvGetChar():
    """Lit un caractère du clavier"""
    return sys.stdin.read(1)

def PvFlushKeyboard():
    """Vide le buffer clavier"""
    while PvKbHit():
        PvGetChar()

def PvGetTickCountMs():
    """Retourne le nombre de millisecondes écoulées depuis le démarrage"""
    return int(time.time() * 1000)

def PvSelectDevice():
    """Détecte automatiquement la première caméra connectée via eBUS."""
    import eBUS as eb

    print("🔍 Recherche de caméras...")

    system = eb.PvSystem()
    system.Find()

    interface_count = system.GetInterfaceCount()
    if interface_count == 0:
        print("❌ Aucune interface réseau détectée.")
        return None

    for i in range(interface_count):
        interface = system.GetInterface(i)
        interface_name = interface.GetName()
        device_count = interface.GetDeviceCount()

        print(f"🌐 Interface {interface_name} : {device_count} caméra(s) détectée(s)")

        if device_count > 0:
            device_info = interface.GetDeviceInfo(0)  # On prend la 1ère caméra
            display_id = device_info.GetDisplayID()
            print(f"✅ Caméra trouvée : {display_id}")
            return display_id

    print("❌ Aucune caméra détectée.")
    return None

class PvMutex:
    def __init__(self):
        self._lock = threading.Lock()

    def Lock(self):
        self._lock.acquire()

    def Unlock(self):
        self._lock.release()

class PvKb:
    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)

    def __del__(self):
        self.stop()

    def kbhit(self):
        '''Retourne True si une touche a été pressée'''
        rlist, _, _ = select.select([sys.stdin], [], [], 0)
        return bool(rlist)

    def getch(self):
        '''Retourne le caractère pressé'''
        return sys.stdin.read(1)

    def stop(self):
        '''Remet le terminal en mode normal'''
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)


