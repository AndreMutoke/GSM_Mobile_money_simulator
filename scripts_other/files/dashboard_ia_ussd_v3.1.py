"""
============================================================
 DASHBOARD USSD - MONITORING TEMPS RÉEL v3.2
 
 Nouveau: Dashboard INTERACTIF avec 5 vues sélectionnables:
   - Mode 1: Répartition des risques (IA)
   - Mode 2: Interventions & Sécurité KYC
   - Mode 3: Matrice de Confusion
   - Mode 4: Performance du Modèle (Précision)
   - Mode 5: Flux d'activité en temps réel
   
 Navigation: Touches 1-5 ou flèches pour changer de vue
============================================================
"""

import curses
import time
import os
import json

FICHIER_LOG = "historique_transactions.log"
FICHIER_CONFUSION = "confusion_matrix.log"

# =========================================================
#  ANALYSE DES LOGS
# =========================================================

def analyser_logs():
    """Lit le fichier de log et extrait les statistiques."""
    stats = {
        "Total": 0, 
        "Léger": 0, 
        "Moyen": 0, 
        "Élevé": 0, 
        "Très élevé": 0,
        "Bloquées_IA": 0,
        "PIN_Echecs": 0,
        "Comptes_Bloques": 0
    }
    toutes_actions = []

    if not os.path.exists(FICHIER_LOG):
        return stats, ["En attente de donnees (fichier log introuvable)..."]

    try:
        with open(FICHIER_LOG, "r", encoding="utf-8") as f:
            lignes = f.readlines()

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

    except Exception:
        pass

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
    
    # Precision = VP / (VP + FP)
    if (metriques["VP"] + metriques["FP"]) > 0:
        metriques["precision"] = metriques["VP"] / (metriques["VP"] + metriques["FP"])
    
    # Rappel = VP / (VP + FN)
    if (metriques["VP"] + metriques["FN"]) > 0:
        metriques["rappel"] = metriques["VP"] / (metriques["VP"] + metriques["FN"])
    
    # F1-Score = 2 * (Precision * Rappel) / (Precision + Rappel)
    if (metriques["precision"] + metriques["rappel"]) > 0:
        metriques["f1"] = 2 * (metriques["precision"] * metriques["rappel"]) / (metriques["precision"] + metriques["rappel"])
    
    return metriques

# =========================================================
#  DESSINER LE DASHBOARD - INTERACTIF
# =========================================================

def dessiner_mode_risques(stdscr, hauteur, largeur, stats):
    """Mode 1: Répartition des risques"""
    stdscr.addstr(4, 2, "┌─ RÉPARTITION DES RISQUES (IA) ─────────────────────────────────────┐", curses.color_pair(5))
    stdscr.addstr(5, 2, "│                                                                     │", curses.color_pair(5))
    
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
    stdscr.addstr(5, 2, "│                                                                     │", curses.color_pair(5))
    
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
    else:
        stdscr.addstr(y, 4, "Taux de blocage IA: N/A", curses.color_pair(1))
    
    y += 2
    stdscr.addstr(y, 4, "Status: Système de sécurité ACTIF ✓", curses.color_pair(1) | curses.A_BOLD)
    
    y += 2
    stdscr.addstr(y, 2, "└─────────────────────────────────────────────────────────────────────┘", curses.color_pair(5))

def dessiner_mode_confusion(stdscr, hauteur, largeur, metriques):
    """Mode 3: Matrice de confusion"""
    stdscr.addstr(4, 2, "┌─ MATRICE DE CONFUSION - CLASSIFICATION ────────────────────────────┐", curses.color_pair(5))
    stdscr.addstr(5, 2, "│                                                                     │", curses.color_pair(5))
    
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
    stdscr.addstr(5, 2, "│                                                                     │", curses.color_pair(5))
    
    y = 6
    
    # Déterminer la couleur en fonction de la précision
    precision_pct = metriques["precision"] * 100
    if precision_pct >= 90:
        couleur_precision = curses.color_pair(1)  # Vert
        etat = "EXCELLENT ✓"
    elif precision_pct >= 75:
        couleur_precision = curses.color_pair(2)  # Jaune
        etat = "BON ◑"
    elif precision_pct >= 60:
        couleur_precision = curses.color_pair(3)  # Magenta
        etat = "ACCEPTABLE"
    else:
        couleur_precision = curses.color_pair(4)  # Rouge
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
    stdscr.addstr(y, 4, f"Formule Précision: VP/(VP+FP) = {metriques['VP']}/({metriques['VP']}+{metriques['FP']})")
    
    y += 2
    stdscr.addstr(y, 4, f"État du modèle: ", curses.A_BOLD)
    stdscr.addstr(y, 21, etat, couleur_precision | curses.A_BOLD)
    
    y += 2
    stdscr.addstr(y, 2, "└─────────────────────────────────────────────────────────────────────┘", curses.color_pair(5))

def dessiner_mode_activite(stdscr, hauteur, largeur, toutes_actions):
    """Mode 5: Flux d'activité en temps réel"""
    stdscr.addstr(4, 2, "┌─ FLUX D'ACTIVITÉ EN TEMPS RÉEL ────────────────────────────────────┐", curses.color_pair(5))
    
    max_lignes_flux = hauteur - 10
    if max_lignes_flux < 1:
        max_lignes_flux = 1
    
    actions_a_afficher = toutes_actions[-max_lignes_flux:] if len(toutes_actions) > max_lignes_flux else toutes_actions
    
    y = 6
    for action in actions_a_afficher:
        couleur = curses.color_pair(5)
        
        if any(mot in action for mot in ["Très", "Alerte Fraude", "ECHEC", "COMPTE_BLOQUE", "est COMPTE_BLOQUE"]):
            couleur = curses.color_pair(4) | curses.A_BOLD
        elif "Élevé" in action or "[SÉCURITÉ]" in action or "Moyen" in action:
            couleur = curses.color_pair(2)
        elif "[IA]" in action or "[Système Défense]" in action:
            couleur = curses.color_pair(3) | curses.A_BOLD
        elif any(mot in action for mot in ["Léger", "SUCCES", "VALIDÉE", "débloqué"]):
            couleur = curses.color_pair(1)
        
        max_longeur = largeur - 6
        action_affichee = action[:max_longeur] if len(action) > max_longeur else action
        
        stdscr.addstr(y, 4, action_affichee, couleur)
        y += 1
    
    stdscr.addstr(hauteur - 2, 2, "└─────────────────────────────────────────────────────────────────────┘", curses.color_pair(5))

def dessiner_dashboard(stdscr):
    """Affiche le dashboard INTERACTIF avec navigation."""
    curses.curs_set(0)
    stdscr.nodelay(True)
    
    # Configuration des couleurs
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)
    
    mode_courant = 1  # Par défaut: Mode 1 (Risques)
    
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
        
        titre_texte = "│  SOC USSD - MONITORING IA TEMPS RÉEL v3.2 - DASHBOARD INTERACTIF  │"
        stdscr.addstr(1, 0, titre_texte, curses.color_pair(6) | curses.A_BOLD)
        
        titre_bas = "└─────────────────────────────────────────────────────────────────────────┘"
        stdscr.addstr(2, 0, titre_bas, curses.color_pair(5))

        # Extraction des données
        stats, toutes_actions = analyser_logs()
        metriques = analyser_confusion_matrix()

        # Afficher le contenu en fonction du mode
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

if __name__ == "__main__":
    try:
        curses.wrapper(dessiner_dashboard)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Erreur d'affichage console : {e}")