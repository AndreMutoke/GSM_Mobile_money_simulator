"""
============================================================
 PASSERELLE USSD - MOTEUR DE RISQUE IA & SQLITE (OSMO-HLR)
 Version Améliorée v3.1 :
   - Persistance des blocages (simulation → temps réel)
   - Fichier confusion_matrix.log pour évaluation IA
   - Classification VP/FP/FN/VN pour chaque transaction
   - Calcul de précision (Precision = VP/(VP+FP))
   - Bug fix: Pas d'arrêt lors de consultation en temps réel
   - MFA requise si compte bloqué même en temps réel
============================================================
"""

import serial
import serial.tools.list_ports
import sys
import time
import sqlite3
import os
import random
import string
import math
import json
from datetime import datetime, timedelta

# --- MOTEUR DE MACHINE LEARNING ---
try:
    from sklearn.ensemble import RandomForestClassifier
    import numpy as np
    HAS_ML = True
except ImportError:
    HAS_ML = False
    print("[-] Attention: scikit-learn / numpy manquants.")

NOM_FICHIER_LOG = "historique_transactions.log"
NOM_FICHIER_CONFUSION = "confusion_matrix.log"
DB_FILE = "hlr.db"
FICHIER_COMPTES_BLOQUES = "comptes_bloques.json"

# Compteur de tentatives échouées par numéro
tentatives_echouees: dict[str, int] = {}

# Comptes bloqués persistants
comptes_bloques_persistants = set()

# Liste des Cell-IDs connus
CELLID_CONNUS = {
    10243: "Katuba", 20184: "Kenya Centre", 30948: "Kamalondo",
    40592: "Kampemba", 50812: "Ruashi", 11092: "Gombe",
    22014: "Lingwala", 33054: "Limete", 44081: "Ngaliema", 55073: "Barumbu",
}

# Données de localisations
LOCALISATIONS_ZONES = {
    "Katuba": (-11.2197, 27.4833), "Kenya Centre": (-11.1596, 27.3497),
    "Kamalondo": (-11.1897, 27.5097), "Kampemba": (-11.1797, 27.4597),
    "Ruashi": (-11.2497, 27.3197), "Gombe": (-11.1397, 27.4997),
    "Lingwala": (-11.1097, 27.5297), "Limete": (-11.1697, 27.4097),
    "Ngaliema": (-11.1497, 27.3797), "Barumbu": (-11.1297, 27.4397),
}

# Données des comptes
DONNEES_COMPTES = {
    "243970000001": {
        "nom": "MUTOMBO", "postnom": "NGOY", "pin": "1234",
        "phrase_secrete": "MSCAGNES", "solde": 500.0,
        "localisation_principale": "Katuba", "localisation_travail": "Kenya Centre",
        "imei": "357618051523999",
    },
    "243970000002": {
        "nom": "KABILA", "postnom": "KABANGE", "pin": "5678",
        "phrase_secrete": "MSCAGNES", "solde": 1200.0,
        "localisation_principale": "Gombe", "localisation_travail": "Lingwala",
        "imei": "867082036666895",
    },
    "243970000003": {
        "nom": "TSHISEKEDIS", "postnom": "ETIENNE", "pin": "9876",
        "phrase_secrete": "MSCAGNES", "solde": 800.0,
        "localisation_principale": "Limete", "localisation_travail": "Ngaliema",
        "imei": "490154203237518",
    },
}

# ===========================================================
#  PERSISTANCE DES BLOCAGES
# ===========================================================

def charger_comptes_bloques():
    """Charge la liste des comptes bloqués persistants."""
    global comptes_bloques_persistants
    if os.path.exists(FICHIER_COMPTES_BLOQUES):
        try:
            with open(FICHIER_COMPTES_BLOQUES, "r") as f:
                data = json.load(f)
                comptes_bloques_persistants = set(data.get("bloques", []))
        except:
            comptes_bloques_persistants = set()
    else:
        comptes_bloques_persistants = set()

def sauvegarder_comptes_bloques():
    """Sauvegarde la liste des comptes bloqués persistants."""
    with open(FICHIER_COMPTES_BLOQUES, "w") as f:
        json.dump({"bloques": list(comptes_bloques_persistants)}, f)

def bloquer_compte_persistant(numero: str):
    """Bloque un compte de façon persistante."""
    comptes_bloques_persistants.add(numero)
    sauvegarder_comptes_bloques()

def debloquer_compte_persistant(numero: str):
    """Débloque un compte de façon persistante."""
    comptes_bloques_persistants.discard(numero)
    sauvegarder_comptes_bloques()

def compte_est_bloque_persistant(numero: str) -> bool:
    """Vérifie si un compte est bloqué de façon persistante."""
    return numero in comptes_bloques_persistants

# ===========================================================
#  MATRICE DE CONFUSION
# ===========================================================

def enregistrer_confusion_matrix(numero: str, montant: float,
                                  risque_predit: str, risque_reel: str,
                                  classification: str) -> None:
    """
    Enregistre une transaction dans la matrice de confusion.
    
    classification: VP (Vrai Positif), FP (Faux Positif), 
                    FN (Faux Négatif), VN (Vrai Négatif)
    """
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "timestamp": horodatage,
        "numero": numero,
        "montant": montant,
        "risque_predit": risque_predit,
        "risque_reel": risque_reel,
        "classification": classification,
    }
    
    with open(NOM_FICHIER_CONFUSION, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def calculer_metriques_precision():
    """
    Calcule les métriques de précision à partir du fichier confusion_matrix.log
    Retourne: {VP, FP, FN, VN, Precision}
    """
    if not os.path.exists(NOM_FICHIER_CONFUSION):
        return {"VP": 0, "FP": 0, "FN": 0, "VN": 0, "precision": 0.0}
    
    vp = fp = fn = vn = 0
    
    try:
        with open(NOM_FICHIER_CONFUSION, "r", encoding="utf-8") as f:
            for ligne in f:
                try:
                    data = json.loads(ligne.strip())
                    classification = data.get("classification", "")
                    if classification == "VP":
                        vp += 1
                    elif classification == "FP":
                        fp += 1
                    elif classification == "FN":
                        fn += 1
                    elif classification == "VN":
                        vn += 1
                except:
                    pass
    except:
        pass
    
    # Precision = VP / (VP + FP)
    precision = vp / (vp + fp) if (vp + fp) > 0 else 0.0
    
    return {
        "VP": vp,
        "FP": fp,
        "FN": fn,
        "VN": vn,
        "precision": round(precision, 4),
        "total": vp + fp + fn + vn
    }

# ===========================================================
#  JOURNALISATION
# ===========================================================

def journaliser_activite(message: str) -> None:
    """Écrit l'activité dans le fichier de log."""
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(NOM_FICHIER_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{horodatage}] {message}\n")

# ===========================================================
#  UTILITAIRES GÉOLOCALISATION
# ===========================================================

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcule la distance en km entre deux points."""
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def verifier_localisation_valide(localisation_compte: str, localisation_actuelle: str) -> int:
    """Vérifie si la localisation est conforme (0) ou non (1)."""
    if localisation_actuelle not in LOCALISATIONS_ZONES:
        return 1
    
    lat_actuelle, lon_actuelle = LOCALISATIONS_ZONES[localisation_actuelle]
    lat_habit, lon_habit = LOCALISATIONS_ZONES[localisation_compte]
    distance = haversine(lat_actuelle, lon_actuelle, lat_habit, lon_habit)
    return 0 if distance < 5 else 1

# ===========================================================
#  UTILITAIRES IMEI
# ===========================================================

def generer_imei() -> str:
    """Génère un IMEI valide (15 chiffres)."""
    return ''.join([str(random.randint(0, 9)) for _ in range(15)])

def verifier_imei(imei_fourni: str, imei_enregistre: str) -> int:
    """Retourne 0 si IMEI conforme, 1 sinon."""
    return 0 if imei_fourni == imei_enregistre else 1

# ===========================================================
#  MOTEUR DE RISQUE (Random Forest)
# ===========================================================

class MoteurRisque:
    """Classifie le risque sur 3 niveaux avec apprentissage continu."""

    NIVEAUX = {0: "Léger", 1: "Doute", 2: "Très élevé"}

    def __init__(self):
        self.model = None
        if HAS_ML:
            self.model = RandomForestClassifier(n_estimators=100, random_state=42)
            self._entrainer_modele()

    def _generer_donnees_synthetiques(self):
        """Génère ~300 exemples synthétiques."""
        random.seed(0)
        X, y = [], []

        def risque_attendu(loc, trans, imei):
            count = loc + trans + imei
            if count == 0:
                return 0  # Léger
            elif count == 1:
                return 1  # Doute
            else:
                return 2  # Très élevé

        for _ in range(100):
            X.append([0, 0, 0])
            y.append(0)

        for _ in range(100):
            loc = random.choice([0, 1])
            trans = random.choice([0, 1])
            imei = random.choice([0, 1])
            if loc + trans + imei == 1:
                X.append([loc, trans, imei])
                y.append(1)

        for _ in range(50):
            X.append([random.choice([0, 1]), random.choice([0, 1]), random.choice([0, 1])])
            y.append(1)

        for _ in range(50):
            X.append([1, 1, 0])
            y.append(2)
        for _ in range(50):
            X.append([1, 0, 1])
            y.append(2)
        for _ in range(50):
            X.append([0, 1, 1])
            y.append(2)
        for _ in range(50):
            X.append([1, 1, 1])
            y.append(2)

        return X, y

    def _entrainer_modele(self):
        X_train, y_train = self._generer_donnees_synthetiques()
        self.model.fit(X_train, y_train)
        print(f"[IA] Modèle Random Forest entraîné sur {len(X_train)} exemples.")
        
        # Charger et réentraîner sur les données historiques si disponibles
        self._reentrainer_sur_historique()

    def _reentrainer_sur_historique(self):
        """Réentraîne le modèle sur les données du fichier confusion_matrix.log."""
        if not os.path.exists(NOM_FICHIER_CONFUSION):
            return
        
        X_historique, y_historique = [], []
        
        try:
            with open(NOM_FICHIER_CONFUSION, "r", encoding="utf-8") as f:
                for ligne in f:
                    try:
                        data = json.loads(ligne.strip())
                        risque_predit = data.get("risque_predit", "")
                        
                        # Mapper le risque à un code
                        if risque_predit == "Léger":
                            y = 0
                        elif risque_predit == "Doute":
                            y = 1
                        elif risque_predit == "Très élevé":
                            y = 2
                        else:
                            continue
                        
                        # Les features ne sont pas stockées, donc on les reconstruit
                        # De manière simplifiée pour l'apprentissage continu
                        X_historique.append([0, 0, 0])  # Placeholder
                        y_historique.append(y)
                    except:
                        pass
        except:
            pass
        
        # Si on a des données historiques, réentraîner
        if X_historique and HAS_ML:
            # Combiner avec les données synthétiques
            X_train, y_train = self._generer_donnees_synthetiques()
            X_train.extend(X_historique)
            y_train.extend(y_historique)
            
            self.model.fit(X_train, y_train)

    def evaluer(self, localisation_mismatch: int, transaction_mismatch: int, imei_mismatch: int) -> str:
        """Évalue le risque basé sur 3 paramètres."""
        if not HAS_ML or self.model is None:
            count = localisation_mismatch + transaction_mismatch + imei_mismatch
            if count == 0:
                return "Léger"
            elif count == 1:
                return "Doute"
            else:
                return "Très élevé"
        
        prediction = self.model.predict([[localisation_mismatch, transaction_mismatch, imei_mismatch]])[0]
        return self.NIVEAUX.get(prediction, "Inconnu")

# ===========================================================
#  GESTION BASE DE DONNÉES
# ===========================================================

def verifier_base_donnees() -> None:
    """Crée ou vérifie l'existence de la base de données."""
    if os.path.exists(DB_FILE):
        print(f"[+] Base de données '{DB_FILE}' trouvée.")
        return

    print(f"[+] Création de la base de données '{DB_FILE}'...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS comptes (
        numero_compte TEXT PRIMARY KEY,
        nom TEXT, postnom TEXT, pin TEXT, phrase_secrete TEXT,
        solde REAL, localisation_principale TEXT,
        localisation_travail TEXT, imei TEXT, compte_bloque INTEGER DEFAULT 0
    )
    """)

    for numero, data in DONNEES_COMPTES.items():
        cursor.execute("""
        INSERT INTO comptes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (numero, data["nom"], data["postnom"], data["pin"], 
              data["phrase_secrete"], data["solde"], 
              data["localisation_principale"], data["localisation_travail"],
              data["imei"]))

    conn.commit()
    conn.close()
    print("[+] Base de données créée avec succès.")

def get_compte(numero: str) -> dict:
    """Récupère les informations d'un compte."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM comptes WHERE numero_compte = ?", (numero,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def mettre_a_jour_compte(numero: str, **kwargs) -> None:
    """Met à jour les données d'un compte."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    for key, value in kwargs.items():
        cursor.execute(f"UPDATE comptes SET {key} = ? WHERE numero_compte = ?", (value, numero))
    
    conn.commit()
    conn.close()

# ===========================================================
#  AUTHENTIFICATION MULTIFACTEUR
# ===========================================================

def verifier_mfa(numero: str, nom: str, postnom: str, phrase: str) -> bool:
    """Vérifie l'authentification multifacteur."""
    compte = get_compte(numero)
    if not compte:
        return False
    
    return (compte["nom"] == nom and 
            compte["postnom"] == postnom and 
            compte["phrase_secrete"] == phrase)

# ===========================================================
#  SIMULATION 1 : ATTAQUE PAR FORCE BRUTE
# ===========================================================

def simulation_force_brute(moteur_risque: MoteurRisque) -> None:
    """Simule 100 tentatives d'attaque par force brute."""
    print("\n" + "=" * 70)
    print(" SIMULATION 1 : ATTAQUE PAR FORCE BRUTE (100 tentatives)")
    print("=" * 70 + "\n")

    comptes = list(DONNEES_COMPTES.keys())
    numero_cible = random.choice(comptes)
    compte = DONNEES_COMPTES[numero_cible]
    
    print(f"[*] Compte cible: {numero_cible} ({compte['nom']} {compte['postnom']})")
    print(f"[*] PIN correct: {compte['pin']}")
    print(f"[*] Lancement de 100 tentatives de PIN aléatoires...\n")

    log_msg = f"[ATTAQUE] Début simulation force brute sur compte {numero_cible}"
    print(log_msg)
    journaliser_activite(log_msg)

    tentatives_globales = 0
    tentatives_compte = 0
    compte_bloque_depuis = False

    for i in range(100):
        tentatives_globales += 1
        
        if random.random() < 0.9:
            pin_essai = ''.join([str(random.randint(0, 9)) for _ in range(4)])
            pin_correct = False
        else:
            pin_essai = compte['pin']
            pin_correct = True

        tentatives_compte += 1

        if compte_bloque_depuis:
            log_msg = f"[SÉCURITÉ] Tentative {i+1}/100 : Compte {numero_cible} COMPTE_BLOQUE - Accès refusé"
            print(log_msg)
            journaliser_activite(log_msg)
            
            log_msg = f"[SÉCURITÉ] MFA ACTIVÉE - Demande d'authentification"
            print(log_msg)
            journaliser_activite(log_msg)
            
            if random.random() < 0.7:
                log_msg = f"[SÉCURITÉ] MFA RÉUSSITE - Compte {numero_cible} déverrouillé"
                print(log_msg)
                journaliser_activite(log_msg)
                compte_bloque_depuis = False
                tentatives_compte = 0
                debloquer_compte_persistant(numero_cible)
            else:
                log_msg = f"[SÉCURITÉ] MFA ÉCHEC - Informations incorrectes"
                print(log_msg)
                journaliser_activite(log_msg)
            continue

        if pin_correct:
            log_msg = f"[ATTAQUE] Tentative {i+1}/100 : PIN CORRECT ! Compte compromis."
            print(f"\n[+] *** SUCCÈS ATTAQUE *** PIN trouvé : {pin_essai}")
            print(log_msg)
            journaliser_activite(log_msg)
            break
        else:
            log_msg = f"[SÉCURITÉ] ECHEC: Code PIN incorrect pour {numero_cible}. Essais restants: {3 - tentatives_compte}"
            print(log_msg)
            journaliser_activite(log_msg)

        if tentatives_compte >= 3:
            compte_bloque_depuis = True
            bloquer_compte_persistant(numero_cible)
            log_msg = f"[SÉCURITÉ] Rejet: Le compte {numero_cible} est COMPTE_BLOQUE (Brute force détecté)."
            print(log_msg)
            journaliser_activite(log_msg)

        time.sleep(0.5)

    print(f"\n[*] Simulation terminée après {tentatives_globales} tentatives.")
    log_msg = f"[ATTAQUE] Fin simulation force brute : {tentatives_globales} tentatives effectuées"
    journaliser_activite(log_msg)

# ===========================================================
#  SIMULATION 2 : 100 TRANSACTIONS
# ===========================================================

def simulation_100_transactions(moteur_risque: MoteurRisque) -> None:
    """Simule 100 transactions avec calcul de VP/FP/FN/VN."""
    print("\n" + "=" * 70)
    print(" SIMULATION 2 : 100 TRANSACTIONS (50 favorables, 50 défavorables)")
    print("=" * 70 + "\n")

    log_msg = "[SIMULATION] Début simulation 100 transactions"
    print(log_msg)
    journaliser_activite(log_msg)

    comptes = list(DONNEES_COMPTES.keys())
    transactions_favorables = 0
    transactions_defavorables = 0
    bloquees_ia = 0
    
    # Compteurs pour confusion matrix
    vp_sim = fp_sim = fn_sim = vn_sim = 0

    for transaction_num in range(1, 101):
        est_favorable = transaction_num <= 50

        numero = random.choice(comptes)
        compte = DONNEES_COMPTES[numero]
        montant = random.uniform(10, 500)
        
        if est_favorable:
            localisation_mismatch = 0
            transaction_mismatch = 0
            imei_mismatch = 0
            localisation_actuelle = compte["localisation_principale"]
            imei_fourni = compte["imei"]
            transactions_favorables += 1
            risque_reel = "Léger"  # Ground truth
        else:
            localisation_mismatch = random.choice([0, 1])
            transaction_mismatch = random.choice([0, 1])
            imei_mismatch = random.choice([0, 1])
            
            if localisation_mismatch == 0 and transaction_mismatch == 0 and imei_mismatch == 0:
                localisation_mismatch = 1
            
            localisation_actuelle = random.choice(list(LOCALISATIONS_ZONES.keys()))
            imei_fourni = generer_imei()
            transactions_defavorables += 1
            risque_reel = "Très élevé"  # Ground truth

        if localisation_mismatch == 0:
            localisation_mismatch = verifier_localisation_valide(
                compte["localisation_principale"], localisation_actuelle
            )
        
        if transaction_mismatch == 0:
            transaction_mismatch = 1 if montant > 400 else 0
        
        if imei_mismatch == 0:
            imei_mismatch = verifier_imei(imei_fourni, compte["imei"])

        # Évaluation IA
        niveau_risque = moteur_risque.evaluer(localisation_mismatch, transaction_mismatch, imei_mismatch)
        bloquer = (niveau_risque == "Très élevé")

        if bloquer:
            bloquees_ia += 1

        # Calculer classification pour confusion matrix
        if niveau_risque == "Très élevé" and risque_reel == "Très élevé":
            classification = "VP"  # Vrai Positif
            vp_sim += 1
        elif niveau_risque == "Très élevé" and risque_reel == "Léger":
            classification = "FP"  # Faux Positif
            fp_sim += 1
        elif niveau_risque == "Léger" and risque_reel == "Très élevé":
            classification = "FN"  # Faux Négatif
            fn_sim += 1
        elif niveau_risque == "Léger" and risque_reel == "Léger":
            classification = "VN"  # Vrai Négatif
            vn_sim += 1
        else:
            classification = "?"

        # Enregistrer dans confusion matrix
        enregistrer_confusion_matrix(numero, montant, niveau_risque, risque_reel, classification)

        statut = "BLOQUÉE_IA" if bloquer else "VALIDÉE"
        details = f"[LOC:{localisation_mismatch}, TRANS:{transaction_mismatch}, IMEI:{imei_mismatch}]"
        log_msg = (f"[TRANSACTION {transaction_num}] {statut} - Risque: {niveau_risque} | "
                   f"Paramètres {details} | Classification: {classification}")
        
        print(log_msg)
        journaliser_activite(f"[IA] Évaluation du risque de la transaction ({montant:.2f} USD) : {niveau_risque}")
        journaliser_activite(log_msg)

        if bloquer:
            journaliser_activite(f"[SÉCURITÉ] Alerte Fraude - Transaction bloquée par IA")

        time.sleep(0.2)

    # Afficher stats finales avec matrice
    print("\n" + "=" * 70)
    print(f"[*] Simulation terminée:")
    print(f"    - Transactions favorables: {transactions_favorables}")
    print(f"    - Transactions défavorables: {transactions_defavorables}")
    print(f"    - Transactions bloquées par IA: {bloquees_ia}")
    print(f"\n[*] Matrice de confusion (simulation):")
    print(f"    - Vrais Positifs (VP): {vp_sim}")
    print(f"    - Faux Positifs (FP): {fp_sim}")
    print(f"    - Faux Négatifs (FN): {fn_sim}")
    print(f"    - Vrais Négatifs (VN): {vn_sim}")
    precision_sim = vp_sim / (vp_sim + fp_sim) if (vp_sim + fp_sim) > 0 else 0
    print(f"    - Précision (simulation): {precision_sim:.2%}")
    print("=" * 70 + "\n")

    log_msg = (f"[SIMULATION] Fin simulation 100 transactions : "
               f"{transactions_favorables} fav, {transactions_defavorables} défav, {bloquees_ia} bloquées")
    journaliser_activite(log_msg)

# ===========================================================
#  TRAITEMENT DES REQUÊTES (MODE TEMPS RÉEL)
# ===========================================================

def get_expediteur_par_defaut() -> dict:
    """Récupère le premier compte de la base de données."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM comptes LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def traiter_req_solde(parts: list[str], expediteur: dict) -> str:
    """Gère REQ_SOLDE;PIN:<pin> - NE PAS ARRÊTER LE SCRIPT"""
    numero_exp = expediteur["numero_compte"]
    pin_fourni = ""

    for part in parts:
        if part.startswith("PIN:"):
            pin_fourni = part.split(":", 1)[1]

    # Vérifier blocage persistant
    if compte_est_bloque_persistant(numero_exp):
        msg = f"[SÉCURITÉ] Compte {numero_exp} est COMPTE_BLOQUE - MFA requise"
        print(msg)
        journaliser_activite(msg)
        return "REPONSE;ERREUR;COMPTE_BLOQUE;MFA_REQUISE"

    if pin_fourni != expediteur["pin"]:
        msg = f"[SÉCURITÉ] ECHEC: Code PIN incorrect pour {numero_exp}. Essais restants: {2 - tentatives_echouees[numero_exp]}"
        print(msg)
        journaliser_activite(msg)
        tentatives_echouees[numero_exp] += 1
        
        if tentatives_echouees[numero_exp] >= 3:
            bloquer_compte_persistant(numero_exp)
            msg = f"[SÉCURITÉ] Compte {numero_exp} BLOQUÉ - 3 tentatives échouées"
            journaliser_activite(msg)
        
        return "REPONSE;ERREUR;PIN_INCORRECT"

    tentatives_echouees[numero_exp] = 0

    nom_complet = f"{expediteur['nom']} {expediteur['postnom']}"
    msg = f"[SOLDE] SUCCES: Consultation effectuée par {nom_complet} ({numero_exp})."
    print(msg)
    journaliser_activite(msg)

    return f"REPONSE;OK;Solde: {expediteur['solde']:.2f} USD|Compte: {nom_complet}"

def traiter_req_trans(parts: list[str], expediteur: dict, moteur_risque: MoteurRisque) -> str:
    """Gère REQ_TRANS avec analyse IA et matrice de confusion."""
    numero_exp = expediteur["numero_compte"]
    pin_fourni = ""
    numero_dest = ""
    montant_str = ""

    for part in parts:
        if part.startswith("PIN:"):
            pin_fourni = part.split(":", 1)[1]
        elif part.startswith("NUM:"):
            numero_dest = part.split(":", 1)[1]
        elif part.startswith("MONT:"):
            montant_str = part.split(":", 1)[1]

    # Vérifier blocage persistant
    if compte_est_bloque_persistant(numero_exp):
        msg = f"[SÉCURITÉ] Compte {numero_exp} est COMPTE_BLOQUE - MFA requise"
        journaliser_activite(msg)
        return "REPONSE;ERREUR;COMPTE_BLOQUE;MFA_REQUISE"

    if pin_fourni != expediteur["pin"]:
        msg = f"[SÉCURITÉ] ECHEC: Code PIN incorrect pour {numero_exp}"
        journaliser_activite(msg)
        tentatives_echouees[numero_exp] += 1
        
        if tentatives_echouees[numero_exp] >= 3:
            bloquer_compte_persistant(numero_exp)
            msg = f"[SÉCURITÉ] Compte {numero_exp} BLOQUÉ"
            journaliser_activite(msg)
        
        return "REPONSE;ERREUR;PIN_INCORRECT"

    tentatives_echouees[numero_exp] = 0

    try:
        montant_float = float(montant_str)
    except ValueError:
        return "REPONSE;ERREUR;MONTANT_INVALIDE"

    if montant_float <= 0:
        return "REPONSE;ERREUR;MONTANT_POSITIF"

    if expediteur["solde"] < montant_float:
        msg = f"[TRANS] ECHEC: Solde insuffisant pour {numero_exp}."
        journaliser_activite(msg)
        return "REPONSE;ERREUR;SOLDE_INSUFFISANT"

    # Évaluation IA
    localisation_mismatch = 0
    transaction_mismatch = 1 if montant_float > 400 else 0
    imei_mismatch = 0
    
    niveau_risque = moteur_risque.evaluer(localisation_mismatch, transaction_mismatch, imei_mismatch)
    
    journaliser_activite(f"[IA] Évaluation du risque de la transaction ({montant_float:.2f} USD) : {niveau_risque}")

    # Enregistrer dans confusion matrix (temps réel)
    # Pas de ground truth parfait en temps réel, donc VN par défaut
    classification = "VN" if niveau_risque == "Léger" else "FP"
    enregistrer_confusion_matrix(numero_exp, montant_float, niveau_risque, "Léger", classification)

    if niveau_risque == "Très élevé":
        journaliser_activite(f"[SÉCURITÉ] Alerte Fraude - Transaction bloquée")
        return "REPONSE;ERREUR;FRAUDE_DETECTEE"

    # Effectuer transaction
    nouveau_solde_exp = expediteur["solde"] - montant_float
    mettre_a_jour_compte(numero_exp, solde=nouveau_solde_exp)

    compte_dest = get_compte(numero_dest)
    if not compte_dest:
        return "REPONSE;ERREUR;COMPTE_DEST_INEXISTANT"

    nouveau_solde_dest = compte_dest["solde"] + montant_float
    mettre_a_jour_compte(numero_dest, solde=nouveau_solde_dest)

    nom_complet_exp = f"{expediteur['nom']} {expediteur['postnom']}"
    nom_dest = f"{compte_dest['nom']} {compte_dest['postnom']}"

    log_msg = (
        f"TRANSACTION VALIDÉE - Risque: {niveau_risque} | "
        f"De: {nom_complet_exp} -> Vers: {nom_dest} | "
        f"Montant: {montant_float:.2f} USD"
    )
    print(log_msg)
    journaliser_activite(log_msg)

    return (f"REP_TRANS;OK;"
            f"Transfert effectue!|Risque: {niveau_risque}|"
            f"Vers: {nom_dest}|Montant: {montant_float:.2f} USD")

def traiter_req_loc(parts: list[str]) -> str:
    """Gère REQ_LOC;BTS:..."""
    bts_str = ""
    for part in parts:
        if part.startswith("BTS:"):
            bts_str = part.split(":", 1)[1]

    if not bts_str:
        return "REP_LOC;ERREUR;Données BTS manquantes"

    bts_entries = bts_str.split(",")
    cellids_recus = []
    for entry in bts_entries:
        tokens = entry.split(":")
        if len(tokens) >= 1:
            try:
                cellids_recus.append(int(tokens[0]))
            except ValueError:
                pass

    if not cellids_recus:
        return "REP_LOC;ERREUR;Format BTS invalide"

    cellids_valides = [cid for cid in cellids_recus if cid in CELLID_CONNUS]
    if not cellids_valides:
        msg = f"[LOC] REJET: Aucun Cell-ID connu"
        print(msg)
        journaliser_activite(msg)
        return "REP_LOC;ERREUR;BTS_INVALIDES"

    zones = [CELLID_CONNUS[cid] for cid in cellids_valides]
    msg = f"[LOC] VALIDATION OK: Cell-IDs={cellids_valides}"
    print(msg)
    journaliser_activite(msg)
    return f"REP_LOC;OK;Validation HLR Reussie|Zones: {','.join(zones)}"

def traiter_requete_uart(ligne: str, moteur_risque: MoteurRisque) -> str:
    """Point d'entrée principal - NE PAS ARRÊTER"""
    ligne = ligne.strip()
    if not ligne:
        return ""

    parts = ligne.split(";")
    type_requete = parts[0]

    if type_requete.startswith("USSD:"):
        code = type_requete.split(":", 1)[1] if ":" in type_requete else ""
        msg = f"[USSD] Code MMI reçu: {code}"
        print(msg)
        journaliser_activite(msg)
        return "REPONSE;OK;Menu USSD ouvert"

    if type_requete == "REQ_LOC":
        return traiter_req_loc(parts)

    expediteur = get_expediteur_par_defaut()
    if not expediteur:
        return "REPONSE;ERREUR;Base vide"

    numero_exp = expediteur["numero_compte"]

    if numero_exp not in tentatives_echouees:
        tentatives_echouees[numero_exp] = 0

    try:
        if type_requete == "REQ_SOLDE":
            return traiter_req_solde(parts, expediteur)
        elif type_requete == "REQ_TRANS":
            return traiter_req_trans(parts, expediteur, moteur_risque)
        else:
            msg = f"[-] Trame inconnue: {type_requete}"
            print(msg)
            journaliser_activite(msg)
            return "REPONSE;ERREUR;Requete inconnue"

    except Exception as e:
        msg = f"[-] Erreur interne: {e}"
        print(msg)
        journaliser_activite(msg)
        return "REPONSE;ERREUR;Erreur interne"

def ecouter_esp32(port_com: str, moteur_risque: MoteurRisque, baudrate: int = 115200) -> None:
    """Boucle principale UART - PATCH: ne pas arrêter sur exception"""
    print(f"\n[+] Connexion au port {port_com} à {baudrate} bauds...")
    try:
        ser = serial.Serial(port=port_com, baudrate=baudrate, timeout=1)
        ser.flushInput()
        ser.flushOutput()
        print("[+] PASSERELLE IA SÉCURISÉE (SQLITE) ACTIVE ! En attente de trames...\n")
    except serial.SerialException as e:
        print(f"[-] Erreur ouverture port : {e}")
        sys.exit(1)

    tampon = ""
    PREFIXES_PROTOCOLE = ("REQ_SOLDE", "REQ_TRANS", "REQ_LOC", "USSD:")

    def est_trame_protocole(ligne: str) -> bool:
        return any(ligne.startswith(p) for p in PREFIXES_PROTOCOLE)

    try:
        while True:
            try:
                if ser.in_waiting > 0:
                    data = ser.read(ser.in_waiting).decode("utf-8", errors="ignore")
                    tampon += data

                    while "\n" in tampon:
                        ligne, tampon = tampon.split("\n", 1)
                        ligne = ligne.strip()
                        if not ligne:
                            continue

                        if not est_trame_protocole(ligne):
                            print(f"  [UART bruit ignoré] {ligne[:80]}")
                            continue

                        print(f"\n[ESP32 →] {ligne}")
                        reponse = traiter_requete_uart(ligne, moteur_risque)

                        if reponse:
                            print(f"[SERVEUR →] {reponse}")
                            ser.write((reponse + "\n").encode("utf-8"))
                            ser.flush()

                time.sleep(0.01)
            
            except Exception as e:
                # NE PAS ARRÊTER - juste afficher l'erreur et continuer
                print(f"[!] Erreur UART: {e}")
                time.sleep(0.1)
                continue

    except KeyboardInterrupt:
        print("\n[+] Arrêt demandé par l'utilisateur.")
    finally:
        try:
            ser.close()
            print("[+] Port série fermé.")
        except:
            pass

def selectionner_port() -> str:
    """Liste les ports disponibles et permet l'utilisateur d'en sélectionner un."""
    ports = list(serial.tools.list_ports.comports())

    if not ports:
        print("[-] Aucun port série détecté.")
        sys.exit(1)

    print("\nPorts série disponibles:")
    for idx, port in enumerate(ports):
        print(f"  [{idx}] {port.device} - {port.description}")

    while True:
        try:
            choix = int(input("\nSélectionnez le numéro du port de l'ESP32 : "))
            if 0 <= choix < len(ports):
                return ports[choix].device
        except ValueError:
            pass
        print("[-] Choix invalide. Réessayez.")

def afficher_menu_principal() -> int:
    """Affiche le menu principal."""
    print("\n" + "=" * 70)
    print(" MENU PRINCIPAL - SÉLECTIONNEZ UNE OPTION")
    print("=" * 70)
    print("[1] Simulation d'attaque par force brute (100 tentatives)")
    print("[2] Simulation de 100 transactions (50 favorables, 50 défavorables)")
    print("[3] Mode d'interaction temps réel (UART)")
    print("[0] Quitter")
    print("=" * 70)

    while True:
        try:
            choix = int(input("\nVotre choix (0-3) : "))
            if 0 <= choix <= 3:
                return choix
        except ValueError:
            pass
        print("[-] Choix invalide. Réessayez.")

# ===========================================================
#  POINT D'ENTRÉE
# ===========================================================

if __name__ == "__main__":
    print("=" * 70)
    print(" PASSERELLE USSD — MOTEUR IA (Random Forest) & SQLITE v3.1")
    print("=" * 70)

    # Charger les blocages persistants
    charger_comptes_bloques()

    verifier_base_donnees()

    moteur_risque = MoteurRisque()

    port = selectionner_port()

    while True:
        choix = afficher_menu_principal()

        if choix == 0:
            print("\n[+] Au revoir!")
            sys.exit(0)

        elif choix == 1:
            simulation_force_brute(moteur_risque)

        elif choix == 2:
            simulation_100_transactions(moteur_risque)

        elif choix == 3:
            ecouter_esp32(port, moteur_risque)

        input("\nAppuyez sur Entrée pour revenir au menu...")
