import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# Toutes les règles (y compris celles avec "mois")
rules_data = {
    'inflationmomlevel:312': [
        {'rule_id': 1, 'score': 0.200499, 'metric1': 0.281818, 'metric2': 0.903226, 'metric3': 0.016422, 'metric4': 1.000000,
         'conditions': ['gdpconstantlevellagged:3']},
        {'rule_id': 2, 'score': 0.227297, 'metric1': 0.181818, 'metric2': 0.900000, 'metric3': 0.016364, 'metric4': 0.999972,
         'conditions': ['tourismrevenuelevellagged:1']},
        {'rule_id': 3, 'score': 0.246746, 'metric1': 0.118182, 'metric2': 0.923077, 'metric3': 0.016783, 'metric4': 0.999527,
         'conditions': ['goldreserveslevellagged:1', 'minwagelevellagged:1']},
        {'rule_id': 4, 'score': 0.252597, 'metric1': 0.100000, 'metric2': 0.909091, 'metric3': 0.016529, 'metric4': 0.997790,
         'conditions': ['goldreserveslevellagged:3', 'minwagelevellagged:2']},
        {'rule_id': 5, 'score': 0.252597, 'metric1': 0.100000, 'metric2': 0.909091, 'metric3': 0.016529, 'metric4': 0.997790,
         'conditions': ['cpilevellagged:1', 'manufacturingprodlevellagged:1', 'unemploymentratelevellagged:1']},
        {'rule_id': 6, 'score': 0.255577, 'metric1': 0.090909, 'metric2': 0.900000, 'metric3': 0.016364, 'metric4': 0.995327,
         'conditions': ['importslevellagged:3', 'moneysupplym2levellagged:2']},
        {'rule_id': 7, 'score': 0.258834, 'metric1': 0.081818, 'metric2': 1.000000, 'metric3': 0.018182, 'metric4': 0.999732,
         'conditions': ['mois:10']},
        {'rule_id': 8, 'score': 0.258834, 'metric1': 0.081818, 'metric2': 1.000000, 'metric3': 0.018182, 'metric4': 0.999732,
         'conditions': ['mois:4']},
        {'rule_id': 9, 'score': 0.264752, 'metric1': 0.063636, 'metric2': 1.000000, 'metric3': 0.018182, 'metric4': 0.998580,
         'conditions': ['exportslevellagged:3', 'moneysupplym2levellagged:2']},
        {'rule_id': 10, 'score': 0.267746, 'metric1': 0.054545, 'metric2': 1.000000, 'metric3': 0.018182, 'metric4': 0.996755,
         'conditions': ['unemploymentratelevellagged:2']},
        {'rule_id': 11, 'score': 0.267746, 'metric1': 0.054545, 'metric2': 1.000000, 'metric3': 0.018182, 'metric4': 0.996755,
         'conditions': ['cpitransportlevellagged:2', 'foodinflationlevellagged:2', 'foreignreserveslevellagged:3', 'miningprodlevellagged:1']},
        {'rule_id': 12, 'score': 0.270756, 'metric1': 0.045455, 'metric2': 1.000000, 'metric3': 0.018182, 'metric4': 0.992585,
         'conditions': ['employedpersonslevellagged:3', 'rentinflationlevellagged:2']}
    ],
    'inflationmomlevel:23': [
        {'rule_id': 1, 'score': 0.267395, 'metric1': 0.054545, 'metric2': 1.000000, 'metric3': 0.019231, 'metric4': 0.997804,
         'conditions': ['mois:2', 'rentinflationlevellagged:1']},
        {'rule_id': 2, 'score': 0.267395, 'metric1': 0.054545, 'metric2': 1.000000, 'metric3': 0.019231, 'metric4': 0.997804,
         'conditions': ['manufacturingprodlevellagged:1', 'miningprodlevellagged:1', 'mois:5']},
        {'rule_id': 3, 'score': 0.270411, 'metric1': 0.045455, 'metric2': 1.000000, 'metric3': 0.019231, 'metric4': 0.994654,
         'conditions': ['exportslevellagged:2', 'mois:12']}
    ]
}

def check_rule_conditions(data_row, conditions):
    """Vérifier si les conditions d'une règle sont satisfaites"""
    for condition in conditions:
        if ':' in condition:
            var_name, threshold = condition.split(':')
            threshold = float(threshold)
            
            if var_name == 'mois':
                # Vérifier le mois
                if 'month' in data_row and data_row['month'] == threshold:
                    continue
                else:
                    return False
            else:
                # Vérifier les autres variables
                if var_name in data_row:
                    if data_row[var_name] >= threshold:
                        continue
                    else:
                        return False
                else:
                    return False
    return True

def apply_rules_to_data(data_df, target_rules):
    """Appliquer les règles à un dataset"""
    results = []
    
    for _, row in data_df.iterrows():
        row_results = {
            'row_index': row.name,
            'predictions': [],
            'confidences': [],
            'applied_rules': []
        }
        
        for rule in target_rules:
            if check_rule_conditions(row.to_dict(), rule['conditions']):
                row_results['predictions'].append(rule['metric2'])  # Precision as prediction
                row_results['confidences'].append(rule['metric4'])  # Confidence
                row_results['applied_rules'].append(rule['rule_id'])
        
        # Moyenne des prédictions si plusieurs règles s'appliquent
        if row_results['predictions']:
            row_results['final_prediction'] = np.mean(row_results['predictions'])
            row_results['final_confidence'] = np.mean(row_results['confidences'])
            row_results['num_rules_applied'] = len(row_results['predictions'])
        else:
            row_results['final_prediction'] = None
            row_results['final_confidence'] = None
            row_results['num_rules_applied'] = 0
        
        results.append(row_results)
    
    return results

def main():
    st.set_page_config(page_title="Model Rules Engine", layout="wide")
    
    st.title("🎯 Model Rules Engine")
    
    # Sidebar navigation
    page = st.sidebar.selectbox("Choose Page", ["📊 Rules Overview", "🔄 Apply Rules to Data"])
    
    if page == "📊 Rules Overview":
        st.header("📊 Rules Overview")
        
        # Afficher toutes les règles par target
        for target, rules in rules_data.items():
            st.subheader(f"🎯 {target}")
            
            # Métriques globales
            precision = np.mean([rule['metric2'] for rule in rules])
            confidence = np.mean([rule['metric4'] for rule in rules])
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Average Precision", f"{precision:.4f}")
            with col2:
                st.metric("Average Confidence", f"{confidence:.4f}")
            with col3:
                st.metric("Total Rules", len(rules))
            
            # Table des règles
            df = pd.DataFrame(rules)
            df['conditions_str'] = df['conditions'].apply(lambda x: ', '.join(x))
            
            display_df = df[['rule_id', 'score', 'metric2', 'metric4', 'conditions_str']].copy()
            display_df.columns = ['Rule ID', 'Score', 'Precision', 'Confidence', 'Conditions']
            
            st.dataframe(display_df, use_container_width=True)
            
            # Graphique
            fig = px.scatter(df, x='metric2', y='metric4', 
                           color='score', size='metric1',
                           hover_data=['rule_id'],
                           title=f"Precision vs Confidence - {target}")
            st.plotly_chart(fig, use_container_width=True)
    
    elif page == "🔄 Apply Rules to Data":
        st.header("🔄 Apply Rules to Data")
        
        # Sélection du target
        selected_target = st.selectbox("Select Target:", list(rules_data.keys()))
        
        st.subheader("📥 Input Data")
        
        # Option 1: Upload CSV
        uploaded_file = st.file_uploader("Upload CSV file", type=['csv'])
        
        # Option 2: Manual input
        st.write("Or enter data manually:")
        
        # Créer des colonnes d'input basées sur les conditions des règles
        all_conditions = set()
        for rule in rules_data[selected_target]:
            for condition in rule['conditions']:
                if ':' in condition:
                    var_name = condition.split(':')[0]
                    all_conditions.add(var_name)
        
        # Interface pour saisie manuelle
        manual_data = {}
        cols = st.columns(3)
        
        for i, var in enumerate(sorted(all_conditions)):
            with cols[i % 3]:
                if var == 'mois':
                    manual_data[var] = st.selectbox(f"{var}:", range(1, 13), key=var)
                else:
                    manual_data[var] = st.number_input(f"{var}:", value=0.0, key=var)
        
        # Bouton pour ajouter une ligne
        if st.button("Add Row to Dataset"):
            if 'manual_dataset' not in st.session_state:
                st.session_state.manual_dataset = []
            st.session_state.manual_dataset.append(manual_data.copy())
        
        # Afficher le dataset manuel
        if 'manual_dataset' in st.session_state and st.session_state.manual_dataset:
            st.write("Manual Dataset:")
            manual_df = pd.DataFrame(st.session_state.manual_dataset)
            st.dataframe(manual_df)
            
            if st.button("Clear Manual Dataset"):
                st.session_state.manual_dataset = []
        
        # Traitement des données
        data_to_process = None
        
        if uploaded_file is not None:
            data_to_process = pd.read_csv(uploaded_file)
        elif 'manual_dataset' in st.session_state and st.session_state.manual_dataset:
            data_to_process = pd.DataFrame(st.session_state.manual_dataset)
        
        if data_to_process is not None:
            st.subheader("📊 Data Preview")
            st.dataframe(data_to_process.head())
            
            if st.button("🚀 Apply Rules", type="primary"):
                with st.spinner("Applying rules..."):
                    results = apply_rules_to_data(data_to_process, rules_data[selected_target])
                
                st.subheader("📈 Results")
                
                # Créer DataFrame des résultats
                results_df = pd.DataFrame([
                    {
                        'Row': r['row_index'],
                        'Final Prediction': r['final_prediction'],
                        'Final Confidence': r['final_confidence'],
                        'Rules Applied': r['num_rules_applied'],
                        'Rule IDs': ', '.join(map(str, r['applied_rules'])) if r['applied_rules'] else 'None'
                    }
                    for r in results
                ])
                
                st.dataframe(results_df, use_container_width=True)
                
                # Statistiques
                valid_predictions = [r for r in results if r['final_prediction'] is not None]
                
                if valid_predictions:
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Rows Processed", len(results))
                    with col2:
                        st.metric("Successful Predictions", len(valid_predictions))
                    with col3:
                        avg_pred = np.mean([r['final_prediction'] for r in valid_predictions])
                        st.metric("Avg Prediction", f"{avg_pred:.4f}")
                    with col4:
                        avg_conf = np.mean([r['final_confidence'] for r in valid_predictions])
                        st.metric("Avg Confidence", f"{avg_conf:.4f}")
                    
                    # Graphique des résultats
                    if len(valid_predictions) > 1:
                        pred_df = pd.DataFrame([
                            {
                                'Row': r['row_index'],
                                'Prediction': r['final_prediction'],
                                'Confidence': r['final_confidence']
                            }
                            for r in valid_predictions
                        ])
                        
                        fig = px.scatter(pred_df, x='Row', y='Prediction', 
                                       color='Confidence', size='Confidence',
                                       title="Predictions by Row")
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No rules were applied to the data. Check your data format and values.")

if __name__ == "__main__":
    main()