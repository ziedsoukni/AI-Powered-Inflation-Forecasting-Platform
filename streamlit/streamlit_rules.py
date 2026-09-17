import streamlit as st
import pandas as pd
import numpy as np

# Configuration de la page
st.set_page_config(page_title="Prédicteur d'Inflation", page_icon="📈")

def check_rule_conditions(row, conditions):
    """Vérifie si toutes les conditions d'une règle sont remplies"""
    for condition in conditions:
        if ':' in condition:
            var_name, required_level = condition.split(':')
            required_level = int(required_level)
            
            # Gestion spéciale pour les mois
            if var_name == 'mois':
                if 'mois' in row and not pd.isna(row['mois']):
                    if int(row['mois']) != required_level:
                        return False
                else:
                    return False
            else:
                # Pour les autres variables, elles sont déjà au format correct dans vos données
                if var_name in row and not pd.isna(row[var_name]):
                    if int(row[var_name]) != required_level:
                        return False
                else:
                    return False
        else:
            return False
    
    return True

def apply_inflation_rules(row):
    """Applique les règles d'inflation pour déterminer le niveau prédit (2 ou 3 uniquement)"""
    
    # Règles pour niveau 3 (inflation élevée) - inflationmomlevel:312
    rules_level_3 = [
        (['gdpconstantlevellagged:3'], 0.200499, "R3-1"),
        (['tourismrevenuelevellagged:1'], 0.227297, "R3-2"),
        (['goldreserveslevellagged:1', 'minwagelevellagged:1'], 0.246746, "R3-3"),
        (['goldreserveslevellagged:3', 'minwagelevellagged:2'], 0.252597, "R3-4"),
        (['cpilevellagged:1', 'manufacturingprodlevellagged:1', 'unemploymentratelevellagged:1'], 0.252597, "R3-5"),
        (['importslevellagged:3', 'moneysupplym2levellagged:2'], 0.255577, "R3-6"),
        (['mois:10'], 0.258834, "R3-7"),
        (['mois:4'], 0.258834, "R3-8"),
        (['exportslevellagged:3', 'moneysupplym2levellagged:2'], 0.264752, "R3-9"),
        (['unemploymentratelevellagged:2'], 0.267746, "R3-10"),
        (['cpitransportlevellagged:2', 'foodinflationlevellagged:2', 'foreignreserveslevellagged:3', 'miningprodlevellagged:1'], 0.267746, "R3-11"),
        (['employedpersonslevellagged:3', 'rentinflationlevellagged:2'], 0.270756, "R3-12")
    ]
    
    # Règles pour niveau 2 (inflation modérée) - inflationmomlevel:23
    rules_level_2 = [
        (['mois:2', 'rentinflationlevellagged:1'], 0.267395, "R2-1"),
        (['manufacturingprodlevellagged:1', 'miningprodlevellagged:1', 'mois:5'], 0.267395, "R2-2"),
        (['exportslevellagged:2', 'mois:12'], 0.270411, "R2-3")
    ]
    
    # Vérifier règles niveau 3
    score_3 = 0
    matched_rules_3 = []
    for conditions, score, rule_name in rules_level_3:
        if check_rule_conditions(row, conditions):
            score_3 += score
            matched_rules_3.append(rule_name)
    
    # Vérifier règles niveau 2
    score_2 = 0
    matched_rules_2 = []
    for conditions, score, rule_name in rules_level_2:
        if check_rule_conditions(row, conditions):
            score_2 += score
            matched_rules_2.append(rule_name)
    
    # Déterminer le niveau final - priorité au niveau 3 si règles activées
    if score_3 > 0 and score_3 >= score_2:
        return 3, score_3, matched_rules_3
    elif score_2 > 0:
        return 2, score_2, matched_rules_2
    else:
        # Aucune règle activée - retourner None pour indiquer "non classifié"
        return None, 0, []

def calculate_accuracy(predicted_levels, actual_levels):
    """Calcule la précision de la prédiction (en excluant les prédictions None)"""
    valid_predictions = [(p, a) for p, a in zip(predicted_levels, actual_levels) if p is not None]
    if len(valid_predictions) == 0:
        return 0
    
    correct = sum(p == a for p, a in valid_predictions)
    return correct / len(valid_predictions)

# Interface Streamlit
st.title("🔮 Prédicteur de Niveau d'Inflation (Niveaux 2 & 3)")
st.write("Uploadez votre fichier .dat pour appliquer les règles et prédire le niveau d'inflation modérée (2) ou élevée (3).")

uploaded_file = st.file_uploader("Choisir un fichier .dat", type=['dat', 'csv', 'txt'])

if uploaded_file is not None:
    try:
        # Lire le fichier ligne par ligne car ce n'est pas un CSV standard
        content = uploaded_file.read().decode('utf-8')
        lines = content.strip().split('\n')
        
        # Parser le format spécial variable:valeur
        data_rows = []
        for line in lines:
            if line.strip():  # Ignorer les lignes vides
                # Diviser par les virgules et créer un dictionnaire
                pairs = line.split(',')
                row_dict = {}
                for pair in pairs:
                    if ':' in pair:
                        key, value = pair.split(':', 1)
                        try:
                            # Essayer de convertir en nombre
                            row_dict[key] = pd.to_numeric(value)
                        except:
                            # Garder comme string si conversion échoue
                            row_dict[key] = value
                data_rows.append(row_dict)
        
        df = pd.DataFrame(data_rows)
        
        st.success(f"✅ Fichier chargé: {len(df)} observations, {len(df.columns)} variables")
        
        # Aperçu des données
        with st.expander("👀 Aperçu des données"):
            st.dataframe(df.head())
            st.write("**Colonnes disponibles:**", list(df.columns))
        
        # Vérifier si la colonne inflationmomlevel existe (pour comparer avec la réalité)
        has_actual_inflation = 'inflationmomlevel' in df.columns
        
        # Appliquer les règles
        st.subheader("🎯 Application des Règles d'Inflation")
        
        with st.spinner("Application des règles en cours..."):
            results = []
            predicted_levels = []
            actual_levels = []
            
            for idx, row in df.iterrows():
                level_pred, score, matched_rules = apply_inflation_rules(row)
                predicted_levels.append(level_pred)
                
                result_row = {
                    'ID': row.get('id', f'obs_{idx+1}'),
                    'Date': row.get('datetime', ''),
                    'Mois': row.get('mois', ''),
                    'Niveau_Prédit': level_pred if level_pred is not None else 'Non classifié',
                    'Score_Total': round(score, 4),
                    'Règles_Activées': ', '.join(matched_rules) if matched_rules else 'Aucune',
                    'Nb_Règles': len(matched_rules)
                }
                
                if has_actual_inflation:
                    actual_level = int(row['inflationmomlevel'])
                    actual_levels.append(actual_level)
                    result_row['Niveau_Réel'] = actual_level
                    if level_pred is not None:
                        result_row['Correct'] = '✅' if level_pred == actual_level else '❌'
                    else:
                        result_row['Correct'] = '⚪' if actual_level == 1 else '❌'  # ⚪ si réel=1 et non classifié
                
                results.append(result_row)
        
        results_df = pd.DataFrame(results)
        
        # Statistiques globales
        st.subheader("📊 Résumé des Résultats")
        
        if has_actual_inflation:
            col1, col2, col3, col4 = st.columns(4)
            accuracy = calculate_accuracy(predicted_levels, actual_levels)
        else:
            col1, col2, col3 = st.columns(3)
        
        with col1:
            niveau_2 = len(results_df[results_df['Niveau_Prédit'] == 2])
            st.metric("🟡 Niveau 2 (Modéré)", niveau_2, f"{niveau_2/len(results_df)*100:.1f}%")
        
        with col2:
            niveau_3 = len(results_df[results_df['Niveau_Prédit'] == 3])
            st.metric("🔴 Niveau 3 (Élevé)", niveau_3, f"{niveau_3/len(results_df)*100:.1f}%")
        
        with col3:
            non_classifie = len(results_df[results_df['Niveau_Prédit'] == 'Non classifié'])
            st.metric("⚪ Non classifié", non_classifie, f"{non_classifie/len(results_df)*100:.1f}%")
        
        if has_actual_inflation:
            with col4:
                st.metric("🎯 Précision", f"{accuracy:.1%}", help="Précision calculée uniquement sur les observations classifiées (niveaux 2 & 3)")
        
        # Score moyen pour les observations classifiées
        classified_df = results_df[results_df['Niveau_Prédit'] != 'Non classifié']
        if len(classified_df) > 0:
            avg_score = classified_df['Score_Total'].mean()
            st.metric("📈 Score Moyen (Classifiés)", f"{avg_score:.4f}")
        
        # Tableau des résultats
        st.subheader("📋 Résultats Détaillés")
        
        # Filtres
        col1, col2 = st.columns(2)
        with col1:
            niveau_filter = st.selectbox("Filtrer par niveau prédit:", 
                                       ['Tous', 2, 3, 'Non classifié'])
        with col2:
            if has_actual_inflation:
                correct_filter = st.selectbox("Filtrer par précision:", 
                                            ['Tous', 'Correct', 'Incorrect', 'Non classifié'])
            else:
                correct_filter = 'Tous'
        
        # Appliquer les filtres
        filtered_df = results_df.copy()
        if niveau_filter != 'Tous':
            filtered_df = filtered_df[filtered_df['Niveau_Prédit'] == niveau_filter]
        
        if has_actual_inflation and correct_filter != 'Tous':
            if correct_filter == 'Correct':
                filtered_df = filtered_df[filtered_df['Correct'] == '✅']
            elif correct_filter == 'Incorrect':
                filtered_df = filtered_df[filtered_df['Correct'] == '❌']
            elif correct_filter == 'Non classifié':
                filtered_df = filtered_df[filtered_df['Correct'] == '⚪']
        
        st.dataframe(filtered_df, use_container_width=True)
        
        # Graphiques
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Distribution des Prédictions")
            pred_counts = results_df['Niveau_Prédit'].value_counts()
            st.bar_chart(pred_counts)
        
        if has_actual_inflation:
            with col2:
                st.subheader("📊 Performance par Niveau Réel")
                # Analyse de performance
                perf_data = []
                for real_level in [1, 2, 3]:
                    subset = results_df[results_df['Niveau_Réel'] == real_level]
                    if len(subset) > 0:
                        correct = len(subset[subset['Correct'] == '✅'])
                        non_classified = len(subset[subset['Correct'] == '⚪'])
                        incorrect = len(subset[subset['Correct'] == '❌'])
                        
                        perf_data.append({
                            'Niveau_Réel': f"Niveau {real_level}",
                            'Correct': correct,
                            'Non_classifié': non_classified,
                            'Incorrect': incorrect,
                            'Total': len(subset)
                        })
                
                perf_df = pd.DataFrame(perf_data)
                st.dataframe(perf_df)
        
        # Analyse temporelle si dates disponibles
        if 'Date' in results_df.columns and results_df['Date'].notna().any():
            st.subheader("📈 Évolution Temporelle")
            results_df['Date'] = pd.to_datetime(results_df['Date'], errors='coerce')
            temporal_df = results_df.dropna(subset=['Date']).sort_values('Date')
            
            # Convertir les prédictions pour le graphique
            temporal_chart = temporal_df.copy()
            temporal_chart['Niveau_Prédit_Num'] = temporal_chart['Niveau_Prédit'].replace('Non classifié', 0)
            
            if has_actual_inflation:
                chart_data = temporal_chart.set_index('Date')[['Niveau_Prédit_Num', 'Niveau_Réel']]
                chart_data.columns = ['Prédit', 'Réel']
            else:
                chart_data = temporal_chart.set_index('Date')[['Niveau_Prédit_Num']]
                chart_data.columns = ['Prédit']
            
            st.line_chart(chart_data)
            st.caption("Note: Non classifié = 0 dans le graphique")
        
        # Export des résultats
        csv_results = results_df.to_csv(index=False)
        st.download_button(
            label="💾 Télécharger les résultats (CSV)",
            data=csv_results,
            file_name="predictions_inflation_niveaux_2_3.csv",
            mime="text/csv"
        )
        
    except Exception as e:
        st.error(f"❌ Erreur lors du traitement: {str(e)}")
        st.write("Détail de l'erreur:", type(e).__name__)

else:
    st.info("👆 Uploadez votre fichier .dat pour commencer l'analyse")

# Documentation
with st.expander("📖 Explication des Règles"):
    st.write("""
    **🎯 Niveau 3 - Inflation Élevée (inflationmomlevel:312)**
    - 12 règles avec scores de 0.200 à 0.271
    - Conditions basées sur GDP, tourisme, réserves d'or, salaires, etc.
    - Règles saisonnières (mois 4 et 10)
    
    **🎯 Niveau 2 - Inflation Modérée (inflationmomlevel:23)**
    - 3 règles spécifiques avec scores autour de 0.267-0.270
    - Conditions liées aux mois 2, 5, et 12
    
    **⚪ Non classifié**
    - Aucune règle des niveaux 2 ou 3 n'est activée
    - Correspond généralement au niveau 1 d'inflation (faible) dans les données réelles
    
    **Logique de classification:**
    - Si des règles de niveau 3 sont activées : Niveau 3
    - Sinon, si des règles de niveau 2 sont activées : Niveau 2  
    - Sinon : Non classifié
    """)

with st.expander("🔧 Format des Données"):
    st.write("""
    Vos données doivent être au format:
    ```
    id:20162,annee:2016,datetime:2016-02-29,mois:2,inflationmomlevel:1,
    cpihousinglevellagged:1,gdpconstantlevellagged:3,...
    ```
    
    Les variables sont déjà converties en niveaux (1, 2, 3) avec les lags appropriés.
    
    **Note importante:** Ce modèle ne prédit que les niveaux 2 et 3 d'inflation. 
    Les observations qui ne déclenchent aucune règle sont marquées comme "Non classifié" 
    et correspondent généralement au niveau 1 (inflation faible).
    """)

with st.expander("📈 Interprétation des Résultats"):
    st.write("""
    **Métriques de Performance:**
    - **Précision**: Calculée uniquement sur les observations classifiées (niveaux 2 & 3)
    - **Non classifié**: Observations ne déclenchant aucune règle (probablement niveau 1)
    - **Score Total**: Somme des scores des règles activées
    
    **Symboles:**
    - ✅ = Prédiction correcte
    - ❌ = Prédiction incorrecte  
    - ⚪ = Non classifié (peut être correct si le niveau réel est 1)
    """)