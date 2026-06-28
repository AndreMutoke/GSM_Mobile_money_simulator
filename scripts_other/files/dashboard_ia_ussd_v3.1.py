"""
============================================================
 DASHBOARD USSD - MONITORING IA TEMPS RÉEL v3.1
 Amélioration :
   - Affichage des métriques de précision (VP, FP, FN, VN)
   - Design plus ergonomique avec séparation claire
   - Affichage du taux de précision en temps réel
   - Indicateurs visuels améliorés
   - Performance optimisée
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
            if "COMPTE_BLOQUE" in ligne or "verrouillé" in ligne or "COMPTE_BLOQUE" in ligne:
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
        "VP": 0,  # Vrai Positif
        "FP": 0,  # Faux Positif
        "FN": 0,  # Faux Négatif
        "VN": 0,  # Vrai Négatif
        "precision": 0.0,
        "total": 0
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
    
    # Calculer précision = VP / (VP + FP)
    if (metriques["VP"] + metriques["FP"]) > 0:
        metriques["precision"] = metriques["VP"] / (metriques["VP"] + metriques["FP"])
    
    return metriques

# =========================================================
#  DESSINER LE DASHBOARD
# =========================================================

def dessiner_dashboard(stdscr):
    """Affiche le dashboard avec design amélioré."""
    curses.curs_set(0)  # Cacher le curseur
    stdscr.nodelay(True)  # Non-bloquant
    
    # Configuration des couleurs
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)    # Léger
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)   # Moyen
    curses.init_pair(3, curses.COLOR_MAGENTA, curses.COLOR_BLACK)  # Élevé
    curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)      # Très élevé
    curses.init_pair(5, curses.COLOR_CYAN, curses.COLOR_BLACK)     # Interface
    curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)     # En-tête
    curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_WHITE)    # Highlight

    while True:
        stdscr.clear()
        hauteur, largeur = stdscr.getmaxyx()

        if hauteur < 24 or largeur < 120:
            stdscr.addstr(0, 0, "TERMINAL TROP PETIT! Min 120x24", curses.color_pair(4))
            stdscr.refresh()
            time.sleep(1)
            continue

        # EN-TÊTE
        titre = "┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐"
        stdscr.addstr(0, 0, titre, curses.color_pair(5))
        
        titre_texte = "│  SOC USSD - MONITORING IA (RANDOM FOREST) & MATRICE DE CONFUSION - TEMPS RÉEL v3.1  │"
        stdscr.addstr(1, 0, titre_texte, curses.color_pair(6) | curses.A_BOLD)
        
        titre_bas = "└─────────────────────────────────────────────────────────────────────────────────────────────────────┘"
        stdscr.addstr(2, 0, titre_bas, curses.color_pair(5))

        # Extraction des données
        stats, toutes_actions = analyser_logs()
        metriques = analyser_confusion_matrix()

        # ===== COLONNE 1 : STATISTIQUES GLOBALES (lignes 3-13) =====
        
        stdscr.addstr(4, 2, "╔════════════════════════════════════════════════════════════╗", curses.color_pair(5))
        stdscr.addstr(5, 2, "║              RÉPARTITION DES RISQUES (IA)                  ║", curses.color_pair(6) | curses.A_BOLD)
        stdscr.addstr(6, 2, "╠════════════════════════════════════════════════════════════╣", curses.color_pair(5))
        
        stdscr.addstr(7, 4, f"Total Transactions : {stats['Total']}", curses.A_BOLD)
        
        stdscr.addstr(9, 4, f"[✓] Risque Léger       : {stats['Léger']:3d}", curses.color_pair(1))
        stdscr.addstr(10, 4, f"[◑] Risque Moyen       : {stats['Moyen']:3d}", curses.color_pair(2))
        stdscr.addstr(11, 4, f"[!] Risque Élevé       : {stats['Élevé']:3d}", curses.color_pair(3))
        stdscr.addstr(12, 4, f"[✗] Risque Très Élevé  : {stats['Très élevé']:3d}", curses.color_pair(4) | curses.A_BOLD)
        
        stdscr.addstr(13, 2, "╚════════════════════════════════════════════════════════════╝", curses.color_pair(5))

        # ===== COLONNE 2 : INTERVENTIONS & SÉCURITÉ (lignes 4-13) =====
        
        col2_x = 65
        stdscr.addstr(4, col2_x, "╔════════════════════════════════════════════════════════════╗", curses.color_pair(5))
        stdscr.addstr(5, col2_x, "║       INTERVENTIONS & SÉCURITÉ KYC                      ║", curses.color_pair(6) | curses.A_BOLD)
        stdscr.addstr(6, col2_x, "╠════════════════════════════════════════════════════════════╣", curses.color_pair(5))
        
        stdscr.addstr(7, col2_x + 2, f"Échecs Code PIN        : {stats['PIN_Echecs']:3d}", curses.color_pair(2))
        stdscr.addstr(8, col2_x + 2, f"Comptes Verrouillés    : {stats['Comptes_Bloques']:3d}", curses.color_pair(4) | curses.A_BOLD)
        stdscr.addstr(9, col2_x + 2, f"Fraudes Bloquées (IA)  : {stats['Bloquées_IA']:3d}", curses.color_pair(4) | curses.A_BOLD)
        
        stdscr.addstr(11, col2_x, "╠════════════════════════════════════════════════════════════╣", curses.color_pair(5))
        stdscr.addstr(12, col2_x + 2, "Taux blocage IA", curses.A_BOLD)
        
        if stats['Total'] > 0:
            taux_blocage = (stats['Très élevé'] / stats['Total']) * 100
            stdscr.addstr(13, col2_x + 2, f"{taux_blocage:.1f}%", curses.color_pair(4))
        else:
            stdscr.addstr(13, col2_x + 2, "0.0%", curses.color_pair(1))
        
        stdscr.addstr(13, col2_x, "╚════════════════════════════════════════════════════════════╝", curses.color_pair(5))

        # ===== MATRICE DE CONFUSION (lignes 15-21) =====
        
        stdscr.addstr(15, 2, "╔════════════════════════════════════════════════════════════╗", curses.color_pair(5))
        stdscr.addstr(16, 2, "║          MATRICE DE CONFUSION - MÉTRIQUES IA              ║", curses.color_pair(6) | curses.A_BOLD)
        stdscr.addstr(17, 2, "╠════════════════════════════════════════════════════════════╣", curses.color_pair(5))
        
        stdscr.addstr(18, 4, f"Vrais Positifs (VP)    : {metriques['VP']:3d}", curses.color_pair(1))
        stdscr.addstr(19, 4, f"Faux Positifs (FP)     : {metriques['FP']:3d}", curses.color_pair(2))
        stdscr.addstr(20, 4, f"Faux Négatifs (FN)     : {metriques['FN']:3d}", curses.color_pair(2))
        stdscr.addstr(21, 4, f"Vrais Négatifs (VN)    : {metriques['VN']:3d}", curses.color_pair(1))
        
        stdscr.addstr(22, 2, "╚════════════════════════════════════════════════════════════╝", curses.color_pair(5))

        # ===== PRÉCISION IA (lignes 15-21, colonne droite) =====
        
        stdscr.addstr(15, col2_x, "╔════════════════════════════════════════════════════════════╗", curses.color_pair(5))
        stdscr.addstr(16, col2_x, "║         PERFORMANCE DU MODÈLE IA - PRÉCISION            ║", curses.color_pair(6) | curses.A_BOLD)
        stdscr.addstr(17, col2_x, "╠════════════════════════════════════════════════════════════╣", curses.color_pair(5))
        
        # Afficher la précision
        precision_pct = metriques["precision"] * 100
        if precision_pct >= 90:
            couleur_precision = curses.color_pair(1)  # Vert
        elif precision_pct >= 75:
            couleur_precision = curses.color_pair(2)  # Jaune
        else:
            couleur_precision = curses.color_pair(4)  # Rouge
        
        stdscr.addstr(18, col2_x + 2, f"Précision: ", curses.A_BOLD)
        precision_str = f"{precision_pct:.2f}%"
        stdscr.addstr(18, col2_x + 13, precision_str, couleur_precision | curses.A_BOLD)
        
        stdscr.addstr(19, col2_x + 2, f"Transactions analysées: {metriques['total']:3d}")
        stdscr.addstr(20, col2_x + 2, f"Formule: VP/(VP+FP) = {metriques['VP']}/({metriques['VP']}+{metriques['FP']})")
        
        stdscr.addstr(21, col2_x + 2, f"État: ", curses.A_BOLD)
        if metriques['precision'] > 0.9:
            etat = "EXCELLENT ✓"
            couleur_etat = curses.color_pair(1)
        elif metriques['precision'] > 0.75:
            etat = "BON ◑"
            couleur_etat = curses.color_pair(2)
        else:
            etat = "À AMÉLIORER !"
            couleur_etat = curses.color_pair(4)
        
        stdscr.addstr(21, col2_x + 8, etat, couleur_etat | curses.A_BOLD)
        stdscr.addstr(21, col2_x, "╚════════════════════════════════════════════════════════════╝", curses.color_pair(5))

        # ===== FLUX D'ACTIVITÉ EN TEMPS RÉEL (bas de l'écran) =====
        
        stdscr.attron(curses.color_pair(5))
        for x in range(largeur):
            stdscr.addstr(23, x, "─")
        stdscr.attroff(curses.color_pair(5))
        
        stdscr.addstr(24, 2, "FLUX D'ACTIVITÉ EN TEMPS RÉEL (derniers événements)", curses.A_BOLD)
        
        # Afficher les derniers événements
        max_lignes_flux = hauteur - 28
        if max_lignes_flux < 1:
            max_lignes_flux = 1
        
        actions_a_afficher = toutes_actions[-max_lignes_flux:] if len(toutes_actions) > max_lignes_flux else toutes_actions
        
        y_flux = 26
        for action in actions_a_afficher:
            couleur = curses.color_pair(5)
            
            if any(mot in action for mot in ["Très", "Alerte Fraude", "ECHEC", "COMPTE_BLOQUE", "verrouillé", "Attaquant"]):
                couleur = curses.color_pair(4) | curses.A_BOLD
            elif "Élevé" in action or "[SÉCURITÉ]" in action or "Moyen" in action:
                couleur = curses.color_pair(2)
            elif "[Système Défense]" in action or "[IA]" in action:
                couleur = curses.color_pair(3) | curses.A_BOLD
            elif any(mot in action for mot in ["Léger", "SUCCES", "VALIDÉE", "débloqué"]):
                couleur = curses.color_pair(1)
            
            max_longeur_ligne = largeur - 4
            action_affichee = action[:max_longeur_ligne]
            
            stdscr.addstr(y_flux, 2, action_affichee, couleur)
            y_flux += 1

        # PIED DE PAGE
        pied = "Appuyez sur 'q' pour quitter | Actualisation: Temps Réel (1/sec) | Mode: Multi-Passerelles"
        stdscr.addstr(hauteur - 1, 2, pied, curses.color_pair(5))

        stdscr.refresh()

        # Quitter avec 'q'
        c = stdscr.getch()
        if c == ord('q') or c == ord('Q'):
            break

        time.sleep(1)  # Actualiser 1x/sec

if __name__ == "__main__":
    try:
        curses.wrapper(dessiner_dashboard)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Erreur d'affichage console : {e}")
