import serial
import serial.tools.list_ports
import sys
import time
from datetime import datetime

def lister_ports_serie():
    """Détecte et liste tous les ports série actifs sur la machine."""
    ports = serial.tools.list_ports.comports()
    return ports

def selectionner_port():
    """Permet à l'utilisateur de choisir le port série de l'ESP32."""
    print("Recherche des ports série disponibles...")
    ports = lister_ports_serie()
    
    if not ports:
        print("[-] Aucun port série détecté. Vérifiez que votre ESP32 est branché.")
        sys.exit(1)
        
    print("\nPorts détectés :")
    for i, port in enumerate(ports):
        print(f"[{i}] {port.device} - {port.description}")
        
    while True:
        try:
            choix = input("\nSélectionnez le numéro du port de votre ESP32 : ")
            idx = int(choix)
            if 0 <= idx < len(ports):
                return ports[idx].device
            else:
                print(f"Veuillez choisir un nombre entre 0 et {len(ports) - 1}")
        except ValueError:
            print("Entrée invalide. Veuillez saisir un nombre.")

def ecouter_esp32(port_com, baudrate=115200):
    """Se connecte au port spécifié et écoute les messages de l'ESP32."""
    print(f"\n[+] Connexion au port {port_com} à {baudrate} bauds...")
    
    try:
        # Initialisation de la connexion série
        ser = serial.Serial(port=port_com, baudrate=baudrate, timeout=1)
        # Flush des buffers d'entrée/sortie pour démarrer proprement
        ser.flushInput()
        ser.flushOutput()
        print("[+] Connexion établie avec succès ! Écoute en cours...\n")
    except serial.SerialException as e:
        print(f"[-] Erreur lors de la connexion au port {port_com} : {e}")
        sys.exit(1) 

    nom_fichier_log = "historique_transactions.log"

    try:
        while True:
            if ser.in_waiting > 0:
                # Lecture d'une ligne transmise par l'ESP32
                ligne_brute = ser.readline()
                try:
                    # Décodage en texte standard UTF-8
                    ligne = ligne_brute.decode('utf-8').rstrip()
                except UnicodeDecodeError:
                    # Fallback si caractères étranges lors du démarrage de l'ESP32
                    ligne = ligne_brute.decode('latin-1', errors='ignore').rstrip()
                
                # Affichage immédiat de la ligne sur le terminal
                print(ligne)
                
                # Si on détecte la ligne de validation d'une transaction, on enregistre dans le fichier log
                if "TRANSACTION USSD MTK Global" in ligne:
                    horodatage = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
                    with open(nom_fichier_log, "a", encoding="utf-8") as f:
                        f.write(f"\n{horodatage} Début de réception transaction :\n")
                
                # Sauvegarde au fil de l'eau des détails de la transaction dans le fichier log
                if any(x in ligne for x in ["Action Clavier", "Option Menu", "Num. Recole", "Montant", "===="]):
                    with open(nom_fichier_log, "a", encoding="utf-8") as f:
                        f.write(ligne + "\n")
                        
            # Légère pause pour libérer le processeur
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print("\n[+] Arrêt de l'écoute demandé par l'utilisateur. Fermeture du .")
    finally:
        ser.close()
        print("[+] Port série fermé. À bientôt !")

if __name__ == "__main__":
    print("==========================================================")
    # Titres et éléments d'affichage conformes aux consignes francophones
    print("          MONITEUR DE TRANSACTION ESP32 UART              ")
    print("==========================================================")
    
    # 1. Sélectionner le port COM interactif
    port_selectionne = selectionner_port()
    
    # 2. Lancement de l'écoute série (Baudrate 115200 par défaut sur ESP32)
    ecouter_esp32(port_selectionne)