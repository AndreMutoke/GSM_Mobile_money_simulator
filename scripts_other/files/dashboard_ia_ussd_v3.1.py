#!/usr/bin/env python3
"""
============================================================
 DASHBOARD USSD v3.3 ULTRA-FINAL
 
 ✅ CORRECTIONS:
    - Crée historique_transactions.log s'il n'existe pas
    - Crée confusion_matrix.log s'il n'existe pas
    - Affiche "En attente..." si vide
    - 5 vues interactives
    - Navigation clavier (1-5, flèches, q)
============================================================
"""

import curses
import time
import os
import json

FICHIER_LOG = "historique_transactions.log"
FICHIER_CONFUSION = "confusion_matrix.log"

# =========================================================
#  CRÉATION DES FICHIERS S'ILS N'EXISTENT PAS
# =========================================================

def creer_fichiers_logs_sils_nexistent_pas():
    """Crée les fichiers logs s'ils n'existent pas."""
    if not os.path.exists(FICHIER_LOG):
        print(f"[*] Création {FICHIER_LOG}...")
        with open(FICHIER_LOG, "w") as f:
            f.write("")
    
    if not os.path.exists(FICHIER_CONFUSION):
        print(f"[*] Création {FICHIER_CONFUSION}...")
        with open(FICHIER_CONFUSION, "w") as f:
            f.write("")

# =========================================================
#  ANALYSE DES LOGS
# =========================================================

def analyser_logs():
    """Lit le fichier de log et extrait les statistiques."""
    stats = {
        "Total": 0, "Léger": 0, "Moyen": 0, "Élevé": 0, "Très élevé": 0,
        "Bloquées_IA": 0, "PIN_Echecs": 0, "Comptes_Bloques": 0
    }
    toutes_actions = []

    if not os.path.exists(FICHIER_LOG):
        return stats, ["En attente de données..."]

    try:
        with open(FICHIER_LOG, "r", encoding="utf-8") as f:
            lignes = f.readlines()

        if not lignes or all(not l.strip() for l in lignes):
            return stats, ["En attente de données..."]

        for ligne in lignes:
            ligne = ligne.strip()
            if not ligne:
                continue

            if "[IA] Évaluation" in ligne:
                stats["Total"] += 1
                if "Léger" in ligne: stats["Léger"] += 1
                elif "Moyen" in ligne: stats["Moyen"] += 1
                elif "Très" in ligne: stats["Très élevé"] += 1
                elif "Élevé" in ligne: stats["Élevé"] += 1

            if "Alerte Fraude" in ligne or "Bloquée_IA" in ligne:
                stats["Bloquées_IA"] += 1
            if "PIN incorrect" in ligne or "Code PIN incorrect" in ligne or "ECHEC: Code PIN" in ligne:
                stats["PIN_Echecs"] += 1
            if "COMPTE_BLOQUE" in ligne or "verrouillé" in ligne or "est COMPTE_BLOQUE" in ligne:
                stats["Comptes_Bloques"] += 1

            toutes_actions.append(ligne)

    except Exception as e:
        print(f"[!] Erreur lecture log: {e}")
        return stats, ["Erreur lecture fichier"]

    return stats, toutes_actions

# =========================================================
#  ANALYSE MATRICE DE CONFUSION
# =========================================================

def analyser_confusion_matrix():
    """Lit le fichier confusion_matrix.log et calcule les métriques."""
    metriques = {
        "VP": 0, "FP": 0, "FN": 0, "VN": 0,
        "precision": 0.0, "rappel": 0.0, "f1": 0.0, "total": 0
    }

    if not os.path.exists(FICHIER_CONFUSION):
        return metriques

    try:
        with open(FICHIER_CONFUSION, "r", encoding="utf-8") as f:
            for ligne in f:
                try:
                    data = json.loads(ligne.strip())
                    classification = data.get("classification", "")
                    
                    if classification == "VP":
                        metriques["VP"] += 1
                    elif classification == "FP":
                        metriques["FP"] += 1
                    elif classification == "FN":
                        metriques["FN"] += 1
                    elif classification == "VN":
                        metriques["VN"] += 1
                except:
                    pass
    except:
        pass

    metriques["total"] = metriques["VP"] + metriques["FP"] + metriques["FN"] + metriques["VN"]
    
    if (metriques["VP"] + metriques["FP"]) > 0:
        metriques["precision"] = metriques["VP"] / (metriques["VP"] + metriques["FP"])
    
    if (metriques["VP"] + metriques["FN"]) > 0:
        metriques["rappel"] = metriques["VP"] / (metriques["VP"] + metriques["FN"])
    
    if (metriques["precision"] + metriques["rappel"]) > 0:
        metriques["f1"] = 2 * (metriques["precision"] * metriques["rappel"]) / (metriques["precision"] + metriques["rappel"])
    
    return metriques

# =========================================================
#  AFFICHAGE DES MODES
# =========================================================

def dessiner_mode_risques(stdscr, hauteur, largeur, stats):
    """Mode 1: Répartition des risques"""
    stdscr.addstr(4, 2, "┌─ RÉPARTITION DES RISQUES (IA) ─────────────────────────────────────┐", curses.color_pair(5))
    
    y = 6
    stdscr.addstr(y, 4, f"Total Transactions: {stats['Total']}", curses.A_BOLD)
    
    y += 2
    stdscr.addstr(y, 4, f"[✓] Risque Léger        : {stats['Léger']:3d}", curses.color_pair(1))
    y += 1
    stdscr.addstr(y, 4, f"[◑] Risque Moyen        : {stats['Moyen']:3d}", curses.color_pair(2))
    y += 1
    stdscr.addstr(y, 4, f"[!] Risque Élevé        : {stats['Élevé']:3d}", curses.color_pair(3))
    y += 1
    stdscr.addstr(y, 4, f"[✗] Risque Très Élevé   : {stats['Très élevé']:3d}", curses.color_pair(4) | curses.A_BOLD)
    
    y += 2
    if stats['Total'] > 0:
        pct_leger = (stats['Léger'] / stats['Total']) * 100
        pct_tres_eleve = (stats['Très élevé'] / stats['Total']) * 100
        stdscr.addstr(y, 4, f"Pourcentage Léger: {pct_leger:.1f}%", curses.color_pair(1))
        y += 1
        stdscr.addstr(y, 4, f"Pourcentage Très élevé: {pct_tres_eleve:.1f}%", curses.color_pair(4))
    
    y += 2
    stdscr.addstr(y, 2, "└─────────────────────────────────────────────────────────────────────┘", curses.color_pair(5))

def dessiner_mode_securite(stdscr, hauteur, largeur, stats):
    """Mode 2: Interventions et sécurité"""
    stdscr.addstr(4, 2, "┌─ INTERVENTIONS & SÉCURITÉ KYC ─────────────────────────────────────┐", curses.color_pair(5))
    
    y = 6
    stdscr.addstr(y, 4, f"Échecs Code PIN          : {stats['PIN_Echecs']:3d}", curses.color_pair(2))
    y += 1
    stdscr.addstr(y, 4, f"Comptes Verrouillés      : {stats['Comptes_Bloques']:3d}", curses.color_pair(4) | curses.A_BOLD)
    y += 1
    stdscr.addstr(y, 4, f"Fraudes Bloquées (IA)    : {stats['Bloquées_IA']:3d}", curses.color_pair(4) | curses.A_BOLD)
    
    y += 2
    if stats['Total'] > 0:
        taux_blocage = (stats['Bloquées_IA'] / stats['Total']) * 100
        stdscr.addstr(y, 4, f"Taux de blocage IA: {taux_blocage:.1f}%", curses.color_pair(4))
    
    y += 2
    stdscr.addstr(y, 4, "Status: Système ACTIF ✓", curses.color_pair(1) | curses.A_BOLD)
    
    y += 2
    stdscr.addstr(y, 2, "└─────────────────────────────────────────────────────────────────────┘", curses.color_pair(5))

def dessiner_mode_confusion(stdscr, hauteur, largeur, metriques):
    """Mode 3: Matrice de confusion"""
    stdscr.addstr(4, 2, "┌─ MATRICE DE CONFUSION - CLASSIFICATION ────────────────────────────┐", curses.color_pair(5))
    
    y = 6
    stdscr.addstr(y, 4, f"Vrais Positifs (VP)      : {metriques['VP']:3d}", curses.color_pair(1))
    y += 1
    stdscr.addstr(y, 4, f"Faux Positifs (FP)       : {metriques['FP']:3d}", curses.color_pair(2))
    y += 1
    stdscr.addstr(y, 4, f"Faux Négatifs (FN)       : {metriques['FN']:3d}", curses.color_pair(2))
    y += 1
    stdscr.addstr(y, 4, f"Vrais Négatifs (VN)      : {metriques['VN']:3d}", curses.color_pair(1))
    
    y += 2
    stdscr.addstr(y, 4, f"Total transactions: {metriques['total']}", curses.A_BOLD)
    
    y += 2
    stdscr.addstr(y, 2, "└─────────────────────────────────────────────────────────────────────┘", curses.color_pair(5))

def dessiner_mode_performance(stdscr, hauteur, largeur, metriques):
    """Mode 4: Performance du modèle"""
    stdscr.addstr(4, 2, "┌─ PERFORMANCE DU MODÈLE IA ─────────────────────────────────────────┐", curses.color_pair(5))
    
    y = 6
    
    precision_pct = metriques["precision"] * 100
    if precision_pct >= 90:
        couleur_precision = curses.color_pair(1)
        etat = "EXCELLENT ✓"
    elif precision_pct >= 75:
        couleur_precision = curses.color_pair(2)
        etat = "BON ◑"
    elif precision_pct >= 60:
        couleur_precision = curses.color_pair(3)
        etat = "ACCEPTABLE"
    else:
        couleur_precision = curses.color_pair(4)
        etat = "À AMÉLIORER !"
    
    stdscr.addstr(y, 4, f"Précision    : ", curses.A_BOLD)
    stdscr.addstr(y, 18, f"{precision_pct:.2f}%", couleur_precision | curses.A_BOLD)
    
    y += 1
    stdscr.addstr(y, 4, f"Rappel       : ", curses.A_BOLD)
    rappel_pct = metriques["rappel"] * 100
    stdscr.addstr(y, 18, f"{rappel_pct:.2f}%", curses.color_pair(1))
    
    y += 1
    stdscr.addstr(y, 4, f"F1-Score     : ", curses.A_BOLD)
    f1_pct = metriques["f1"] * 100
    stdscr.addstr(y, 18, f"{f1_pct:.2f}%", curses.color_pair(2))
    
    y += 2
    stdscr.addstr(y, 4, f"État: ", curses.A_BOLD)
    stdscr.addstr(y, 11, etat, couleur_precision | curses.A_BOLD)
    
    y += 2
    stdscr.addstr(y, 2, "└─────────────────────────────────────────────────────────────────────┘", curses.color_pair(5))

def dessiner_mode_activite(stdscr, hauteur, largeur, toutes_actions):
    """Mode 5: Flux d'activité en temps réel"""
    stdscr.addstr(4, 2, "┌─ FLUX D'ACTIVITÉ EN TEMPS RÉEL ────────────────────────────────────┐", curses.color_pair(5))
    
    max_lignes = hauteur - 10
    if max_lignes < 1:
        max_lignes = 1
    
    actions = toutes_actions[-max_lignes:] if len(toutes_actions) > max_lignes else toutes_actions
    
    y = 6
    for action in actions:
        couleur = curses.color_pair(5)
        
        if any(mot in action for mot in ["Très", "Alerte Fraude", "ECHEC", "COMPTE_BLOQUE", "est COMPTE_BLOQUE"]):
            couleur = curses.color_pair(4) | curses.A_BOLD
        elif "Élevé" in action or "[SÉCURITÉ]" in action:
            couleur = curses.color_pair(2)
        elif "[IA]" in action:
            couleur = curses.color_pair(3) | curses.A_BOLD
        elif any(mot in action for mot in ["Léger", "SUCCES", "VALIDÉE"]):
            couleur = curses.color_pair(1)
        
        max_len = largeur - 6
        action_affichee = action[:max_len] if len(action) > max_len else action
        
        stdscr.addstr(y, 4, action_affichee, couleur)
        y += 1
    
    stdscr.addstr(hauteur - 2, 2, "└─────────────────────────────────────────────────────────────────────┘", curses.color_pair(5))

# =========================================================
#  BOUCLE PRINCIPALE
# =========================================================

def dessiner_dashboard(stdscr):
    """Affiche le dashboard INTERACTIF."""
    curses.curs_set(0)
    stdscr.nodelay(True)
    
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)
    
    mode_courant = 1
    
    noms_modes = {
        1: "Répartition des risques",
        2: "Interventions & Sécurité",
        3: "Matrice de Confusion",
        4: "Performance du Modèle",
        5: "Flux d'Activité"
    }

    while True:
        stdscr.clear()
        hauteur, largeur = stdscr.getmaxyx()

        if hauteur < 24 or largeur < 80:
            stdscr.addstr(0, 0, "TERMINAL TROP PETIT! Min 80x24", curses.color_pair(4))
            stdscr.refresh()
            time.sleep(1)
            continue

        # EN-TÊTE
        titre = "┌─────────────────────────────────────────────────────────────────────────┐"
        stdscr.addstr(0, 0, titre, curses.color_pair(5))
        
        titre_texte = "│  SOC USSD - MONITORING IA TEMPS RÉEL v3.3 - DASHBOARD INTERACTIF  │"
        stdscr.addstr(1, 0, titre_texte, curses.color_pair(6) | curses.A_BOLD)
        
        titre_bas = "└─────────────────────────────────────────────────────────────────────────┘"
        stdscr.addstr(2, 0, titre_bas, curses.color_pair(5))

        # Extraction des données
        stats, toutes_actions = analyser_logs()
        metriques = analyser_confusion_matrix()

        # Afficher le contenu
        if mode_courant == 1:
            dessiner_mode_risques(stdscr, hauteur, largeur, stats)
        elif mode_courant == 2:
            dessiner_mode_securite(stdscr, hauteur, largeur, stats)
        elif mode_courant == 3:
            dessiner_mode_confusion(stdscr, hauteur, largeur, metriques)
        elif mode_courant == 4:
            dessiner_mode_performance(stdscr, hauteur, largeur, metriques)
        elif mode_courant == 5:
            dessiner_mode_activite(stdscr, hauteur, largeur, toutes_actions)

        # MENU DE NAVIGATION
        menu_y = hauteur - 3
        menu = f"[1] Risques | [2] Sécurité | [3] Confusion | [4] Performance | [5] Activité | [q] Quitter"
        stdscr.attron(curses.color_pair(6))
        stdscr.addstr(menu_y, 0, menu.center(largeur)[:largeur])
        stdscr.attroff(curses.color_pair(6))
        
        # INDICATEUR MODE COURANT
        mode_texte = f"Mode: {noms_modes[mode_courant]}"
        stdscr.addstr(hauteur - 1, 2, mode_texte, curses.A_BOLD)

        stdscr.refresh()

        # Gestion des touches
        c = stdscr.getch()
        if c == ord('q') or c == ord('Q'):
            break
        elif c == ord('1'):
            mode_courant = 1
        elif c == ord('2'):
            mode_courant = 2
        elif c == ord('3'):
            mode_courant = 3
        elif c == ord('4'):
            mode_courant = 4
        elif c == ord('5'):
            mode_courant = 5
        elif c == curses.KEY_RIGHT:
            mode_courant = mode_courant % 5 + 1
        elif c == curses.KEY_LEFT:
            mode_courant = (mode_courant - 2) % 5 + 1

        time.sleep(1)

# =========================================================
#  POINT D'ENTRÉE
# =========================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print(" DASHBOARD USSD v3.3 ULTRA-FINAL")
    print("=" * 70)
    
    print("[*] Vérification des fichiers logs...")
    creer_fichiers_logs_sils_nexistent_pas()
    print("[✓] Fichiers logs prêts")
    
    print("\n[*] Lancement du dashboard...")
    print("[+] Touches: 1-5 pour naviguer, flèches gauche/droite, [q] pour quitter\n")
    
    time.sleep(1)
    
    try:
        curses.wrapper(dessiner_dashboard)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Erreur: {e}")
    
    print("\n[+] Dashboard fermé.")