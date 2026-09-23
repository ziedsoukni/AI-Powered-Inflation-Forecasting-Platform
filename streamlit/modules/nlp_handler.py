import pandas as pd
import numpy as np
import os
import re
import logging
from rapidfuzz import fuzz
import joblib
import spacy
from typing import List, Dict, Tuple, Optional, Union, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline
from functools import lru_cache
from datetime import datetime
import warnings
import streamlit as st

# Chemins portables (relatifs au dossier streamlit/)
from pathlib import Path as _Path
_APP_DIR = _Path(__file__).resolve().parent.parent
DATA_DIR = _APP_DIR / "data"
MODELS_DIR = _APP_DIR / "models"

# === CONFIG LOGGING ===
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === DATA MANAGER (LOCAL) ===
class DataManager:
    def __init__(self, parquet_path: str):
        self.parquet_path = parquet_path
        self.df = pd.DataFrame()
        self.available_cols = []

    def load_data(self) -> bool:
        try:
            self.df = pd.read_parquet(self.parquet_path)
            if 'Datetime' not in self.df.columns:
                raise ValueError("La colonne 'Datetime' est requise")
            self.df['Datetime'] = pd.to_datetime(self.df['Datetime'])
            self.available_cols = list(self.df.columns)
            logger.info(f"Données chargées ({len(self.df)} lignes, {len(self.df.columns)} colonnes)")
            return True
        except Exception as e:
            logger.error(f"Erreur de chargement: {str(e)}")
            return False

# === CONFIGURATION ===
class ConfigManager:
    def __init__(self):
        self.models_dir = str(MODELS_DIR)
        os.makedirs(self.models_dir, exist_ok=True)
        self.variables_synonyms = self._load_variables_synonyms()
        self.operations_dict = self._load_operations_dict()
        self.mois_dict = self._load_mois_dict()

    def _load_variables_synonyms(self) -> Dict[str, List[str]]:
        return {
                    'inflation_mom': [
        'inflation', 'inflation mensuelle', 'hausse des prix', 'augmentation des prix', 
        'ipc', 'indice des prix à la consommation', 'indice des prix', 'prix à la consommation', 
        'inflation mois', 'monthly inflation', 'price index'
    ],
    'cpi': [
        'ipc', 'indice prix consommation', 'indice des prix', 'cpi', 'indice général des prix', 
        'indice de l’inflation', 'consumer price index', 'cpi général'
    ],
    'cpi_housing': [
        'prix logement', 'logement', 'cpi logement', 'coût logement', 'indice logement', 
        'housing index', 'housing cpi', 'logement inflation'
    ],
    'cpi_transport': [
        'prix transport', 'transport', 'transportation index', 'transport inflation', 
        'cpi transport', 'coût du transport'
    ],
    'food_inflation': [
        'inflation alimentaire', 'prix nourriture', 'nourriture', 'prix des aliments', 
        'prix alimentaires', 'food inflation', 'prix denrées', 'indice alimentaire'
    ],
    'rent_inflation': [
        'inflation loyer', 'loyer', 'coût du loyer', 'hausse des loyers', 
        'rent inflation', 'prix location'
    ],
    'exports': [
        'exportations', 'export', 'valeur exportée', 'ventes à l’étranger', 
        'exports', 'commerce extérieur export', 'exportations totales'
    ],
    'imports': [
        'importations', 'import', 'achats étrangers', 'marchandises importées', 
        'imports', 'commerce extérieur import', 'importations totales'
    ],
    'foreign_reserves': [
        'réserves étrangères', 'réserves en devises', 'devises', 
        'réserves monétaires', 'foreign reserves', 'réserves de change'
    ],
    'gold_reserves': [
        'réserves d’or', 'réserve en or', 'stock d’or', 'gold reserves'
    ],
    'external_debt': [
        'dette extérieure', 'dette externe', 'external debt', 'endettement externe', 
        'dette internationale'
    ],
    'industrial_prod_mom': [
        'production industrielle', 'industrie', 'indice industrie', 
        'industrial production', 'production secteur industriel'
    ],
    'manufacturing_prod': [
        'production manufacturière', 'manufacture', 'industrie manufacturière', 
        'manufacturing production', 'fabrication industrielle'
    ],
    'mining_prod': [
        'production minière', 'mine', 'mining', 'extraction minière', 
        'mining production', 'secteur minier'
    ],
    'unemployment_rate': [
        'chômage', 'taux de chômage', 'personnes sans emploi', 
        'unemployment rate', 'niveau de chômage'
    ],
    'employed_persons': [
        'employés', 'emploi', 'personnes employées', 'population active', 
        'working people', 'employed population'
    ],
    'min_wage': [
        'salaire minimum', 'smic', 'salaire', 'minimum wage', 
        'rémunération minimale', 'revenu minimum'
    ],
    'interest_rate': [
        'taux intérêt', 'taux d’intérêt', 'intérêt', 'interest rate', 
        'taux directeur', 'coût du crédit'
    ],
    'money_supply_m1': [
        'masse monétaire m1', 'm1', 'monnaie m1', 'money supply m1', 
        'liquidité immédiate'
    ],
    'money_supply_m2': [
        'masse monétaire m2', 'm2', 'monnaie m2', 'money supply m2', 
        'liquidité élargie'
    ],
    'money_supply_m3': [
        'masse monétaire m3', 'm3', 'monnaie m3', 'money supply m3', 
        'agrégat monétaire m3'
    ],
    'gdp': [
        'pib', 'produit intérieur brut', 'gdp', 'croissance économique', 
        'activité économique', 'valeur ajoutée nationale'
    ],
    'gdp_constant': [
        'pib constant', 'pib réel', 'produit intérieur brut constant', 
        'real gdp', 'croissance économique ajustée'
    ],
    'gov_spending': [
        'dépenses gouvernement', 'dépenses publiques', 'dépenses de l’État', 
        'gouvernement', 'budget de l’État', 'government spending'
    ],
    'consumer_spending': [
        'dépenses consommation', 'consommation', 'dépenses ménages', 
        'consumer spending', 'achats des ménages'
    ],
    'population': [
        'population', 'habitants', 'nombre d’habitants', 
        'population totale', 'démographie'
    ],
    'tourism_revenue': [
        'tourisme', 'revenus tourisme', 'recettes touristiques', 
        'tourism revenue', 'revenus du secteur touristique'
    ]
        }

    def _load_operations_dict(self) -> Dict[str, str]:
        return {     
            'maximum': 'MAX', 'maximums': 'MAX', 'minimum': 'MIN', 'minimums': 'MIN',
            'moyenne': 'AVG', 'moyennes': 'AVG', 'moyen': 'AVG', 'moyens': 'AVG',
            'somme': 'SUM', 'sommes': 'SUM', 'total': 'SUM', 'totaux': 'SUM',
            'plus haut': 'MAX', 'plus bas': 'MIN', 'mean': 'AVG',
            'max': 'MAX', 'min': 'MIN', 'sum': 'SUM', 'médiane': 'MEDIAN'
        }

    def _load_mois_dict(self) -> Dict[str, int]:
        return {
            'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5,
            'juin': 6, 'juillet': 7, 'août': 8, 'septembre': 9,
            'octobre': 10, 'novembre': 11, 'décembre': 12
        }

# === CLASSIFICATEURS ML ===
class BaseClassifier:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        self.is_trained = False

    def save(self) -> None:
        try:
            joblib.dump(self.model, self.model_path)
            logger.info(f"Modèle sauvegardé: {self.model_path}")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du modèle: {str(e)}")

    def load(self) -> bool:
        try:
            if os.path.exists(self.model_path):
                self.model = joblib.load(self.model_path)
                self.is_trained = True
                return True
            return False
        except Exception as e:
            logger.error(f"Erreur lors du chargement du modèle: {str(e)}")
            return False

class VariableClassifier(BaseClassifier):
    def __init__(self, model_path: str):
        super().__init__(model_path)
        self.pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(ngram_range=(1, 2), max_features=5000)),
            ('clf', LinearSVC(C=1.0, class_weight='balanced'))
        ])
        self.label_map = []

    def train(self, X: List[str], y: List[str]) -> None:
        try:
            self.label_map = sorted(set(y))
            self.pipeline.fit(X, y)
            self.model = self.pipeline
            self.is_trained = True
            self.save()
        except Exception as e:
            logger.error(f"Erreur lors de l'entraînement: {str(e)}")

    def predict(self, text: str) -> Tuple[Optional[str], float]:
        if not self.is_trained:
            return None, 0.0
        try:
            prediction = self.model.predict([text])[0]
            return prediction, 1.0
        except Exception as e:
            logger.error(f"Erreur de prédiction: {str(e)}")
            return None, 0.0

class OperationClassifier(VariableClassifier):
    pass

# === NLP Processor ===
class NLPProcessor:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.var_clf = VariableClassifier(os.path.join(config.models_dir, "var_classifier.joblib"))
        self.op_clf = OperationClassifier(os.path.join(config.models_dir, "op_classifier.joblib"))
        try:
            self.nlp = spacy.load("fr_core_news_sm")
        except OSError:
            logger.error("Modèle spaCy 'fr_core_news_sm' non trouvé. Veuillez l'installer.")
            raise

        if not self.var_clf.load():
            logger.warning("Classifieur de variables non chargé")
        if not self.op_clf.load():
            logger.warning("Classifieur d'opérations non chargé")

    @lru_cache(maxsize=1000)
    def normalize_text(self, text: str) -> str:
        return re.sub(r'[^\w\s]', ' ', text.lower()).strip()

    def detect_variables(self, question: str) -> List[str]:
        best_var = None
        best_score = 85
        norm_text = self.normalize_text(question)
        
        for var, syns in self.config.variables_synonyms.items():
            for syn in syns:
                score = fuzz.partial_ratio(norm_text, self.normalize_text(syn))
                if score > best_score:
                    best_var = var
                    best_score = score
        
        return [best_var] if best_var else []

    def detect_operations(self, question: str) -> List[str]:
        norm_text = self.normalize_text(question)
        for op_word, op_code in self.config.operations_dict.items():
            if op_word in norm_text:
                return [op_code]
        return ['select']

    def detect_time_filters(self, question: str) -> Dict[str, Any]:
        filters = {}
        norm_text = self.normalize_text(question)
        
        # Détection de tous les mois mentionnés
        months = []
        for mois, num in self.config.mois_dict.items():
            if mois in norm_text:
                months.append(num)
        if months:
            filters['month'] = months

        # Détection de toutes les années mentionnées (ex : "2019, 2020 et 2021")
        years = re.findall(r'20\d{2}|19\d{2}', norm_text)
        years_int = list(set(int(y) for y in years))
        if years_int:
            filters['year'] = years_int
        
        return filters

# === Query Builder ===
class QueryExecutor:
    def __init__(self, df: pd.DataFrame):
        self.df = df if df is not None else pd.DataFrame()

    def query(self, variable: str, op: str, filters: Dict) -> Union[str, float, pd.DataFrame]:
        if not isinstance(self.df, pd.DataFrame) or self.df.empty:
            return "❌ Aucune donnée disponible"
            
        if variable not in self.df.columns:
            return f"❌ Variable inconnue: {variable}"

        df_filtered = self.df.copy()
        
        # Application des filtres temporels avec listes
        if 'year' in filters:
            if isinstance(filters['year'], list):
                df_filtered = df_filtered[df_filtered['Datetime'].dt.year.isin(filters['year'])]
            else:
                df_filtered = df_filtered[df_filtered['Datetime'].dt.year == filters['year']]
        if 'month' in filters:
            if isinstance(filters['month'], list):
                df_filtered = df_filtered[df_filtered['Datetime'].dt.month.isin(filters['month'])]
            else:
                df_filtered = df_filtered[df_filtered['Datetime'].dt.month == filters['month']]
            
        if df_filtered.empty:
            return "❌ Aucune donnée correspondant aux critères de filtrage"

        # Exécution de l'opération
        if op == 'select':
            # Tri par date croissante
            result_df = df_filtered[['Datetime', variable]].sort_values('Datetime', ascending=True).reset_index(drop=True)
            result_df['Datetime'] = result_df['Datetime'].dt.strftime('%Y-%m-%d')

            return result_df

        if op.upper() in ['MAX', 'MIN', 'SUM', 'AVG', 'MEDIAN']:
            try:
                if op.upper() == 'AVG':
                    return df_filtered[variable].mean()
                elif op.upper() == 'MAX':
                    return df_filtered[variable].max()
                elif op.upper() == 'MIN':
                    return df_filtered[variable].min()
                elif op.upper() == 'SUM':
                    return df_filtered[variable].sum()
                elif op.upper() == 'MEDIAN':
                    return df_filtered[variable].median()
            except Exception as e:
                return f"❌ Erreur lors du calcul: {str(e)}"
                
        return "❌ Opération non supportée"



# === SYSTEME GLOBAL ===
class EconomicSystem:
    def __init__(self, parquet_path: str):
        self.config = ConfigManager()
        self.data = DataManager(parquet_path)
        self.processor = NLPProcessor(self.config)

    def initialize(self) -> bool:
        return self.data.load_data()

    def ask(self, question: str) -> Union[str, float, pd.DataFrame]:
        if not question.strip():
            return "❌ Question vide"
            
        vars_ = self.processor.detect_variables(question)
        ops_ = self.processor.detect_operations(question)
        filters = self.processor.detect_time_filters(question)

        if not vars_:
            return "❌ Aucune variable détectée"
            
        var = vars_[0]
        op = ops_[0] if ops_ else 'select'

        executor = QueryExecutor(self.data.df)
        return executor.query(var, op, filters)

# === UTILISATION ===
if __name__ == "__main__":
    # Configuration pandas pour l'affichage
    pd.set_option('display.max_rows', None)

    pd.set_option('display.max_columns', 20)
    pd.set_option('display.width', 120)
    pd.set_option('display.float_format', '{:.2f}'.format)

    chemin_parquet = str(DATA_DIR / "final401.parquet")
    system = EconomicSystem(chemin_parquet)

    if system.initialize():
        print("\n✅ Système prêt. Posez vos questions.")
        print("👉 Exemples :")
        print("   - Quel était le taux de chômage en 2022 ?")
        print("   - Inflation en janvier 2023")
        print("   - Somme des exportations 2021")
        print("🛑 Tapez 'exit' ou 'quit' pour quitter.\n")

        while True:
            try:
                ligne = input("❓ Vos questions : ").strip()
                if ligne.lower() in ["exit", "quit"]:
                    print("👋 Fin du système.")
                    break

                if not ligne:
                    print("⚠️ Veuillez poser une question.")
                    continue

                # Traitement des questions multiples
                questions = [q.strip() for q in re.split(r"\s*(?:et|ou|,)\s*", ligne) if q.strip()]
                
                print("\n🔍 Résultats :\n")
                for idx, q in enumerate(questions, 1):
                    print(f"🟦 Q{idx}: {q}")
                    try:
                        reponse = system.ask(q)
                        print(f"✅ Réponse :\n{reponse}")
                    except Exception as e:
                        print(f"❌ Erreur : {str(e)}")
                    print("-" * 60)
                    
            except KeyboardInterrupt:
                print("\n👋 Fin du système.")
                break
            except Exception as e:
                print(f"❌ Erreur inattendue : {str(e)}")
                


def run_nlp_analysis(query):
    chemin_parquet = str(DATA_DIR / "final401.parquet")
    system = EconomicSystem(chemin_parquet)
    if system.initialize():
        # Découpe en questions multiples
        questions = [q.strip() for q in re.split(r"\s*(?:et|ou|,)\s*", query) if q.strip()]
        
        st.markdown("### Résultats de l'analyse NLP")

        for idx, q in enumerate(questions, 1):
            st.markdown(f"**Question {idx} :** {q}")
            result = system.ask(q)
            st.write(result)
            st.markdown("---")
    else:
        st.error("Erreur lors du chargement des données.")

# Si variable globale 'query' injectée (via load_module), lance l'analyse
if 'query' in globals() and isinstance(globals()['query'], str) and globals()['query'].strip():
    run_nlp_analysis(globals()['query'])
