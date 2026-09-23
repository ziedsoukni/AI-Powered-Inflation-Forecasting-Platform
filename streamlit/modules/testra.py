import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import logging
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from sklearn.model_selection import cross_val_score
import joblib
import os
import warnings
warnings.filterwarnings('ignore')
import streamlit as st

# Chemins portables (relatifs au dossier streamlit/)
from pathlib import Path as _Path
_APP_DIR = _Path(__file__).resolve().parent.parent
DATA_DIR = _APP_DIR / "data"
MODELS_DIR = _APP_DIR / "models"

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InflationRFPredictor:
    def __init__(self, model_dir=str(MODELS_DIR)):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_cols = []
        self.all_features = []
        self.feature_importance = {}
        self.feature_correlations = {}
        self.model_metrics = {}
        self.model_dir = model_dir
        self.model_path = os.path.join(model_dir, "inflation_rf_model.pkl")
        os.makedirs(model_dir, exist_ok=True)
    
    def load_and_prepare_data(self, parquet_path: str):
        """Charge et prépare les données avec validation"""
        logger.info(f"📥 Chargement des données depuis {parquet_path}")
        
        if not os.path.exists(parquet_path):
            raise FileNotFoundError(f"Fichier non trouvé: {parquet_path}")
        
        self.df = pd.read_parquet(parquet_path)
        
        # Validation des colonnes essentielles
        required_cols = ["inflation_mom", "annee", "mois"]
        missing_cols = [col for col in required_cols if col not in self.df.columns]
        if missing_cols:
            raise ValueError(f"Colonnes manquantes: {missing_cols}")
        
        # Identifier les features numériques
        exclude_cols = ["inflation_mom", "annee", "mois"]
        self.feature_cols = [col for col in self.df.columns 
                           if col not in exclude_cols and pd.api.types.is_numeric_dtype(self.df[col])]
        
        logger.info(f"✅ {len(self.df)} lignes, {len(self.feature_cols)} features identifiées")
        return self.df
    
    def add_lag_features(self, target_col="inflation_mom", max_lag=6):
        """Ajoute des features de lag et features dérivées"""
        logger.info(f"🕰️ Ajout des lags (1 à {max_lag}) et features dérivées")
        
        df_sorted = self.df.sort_values(["annee", "mois"]).reset_index(drop=True)
        
        # Ajouter les lags
        for lag in range(1, max_lag + 1):
            df_sorted[f"lag_{lag}"] = df_sorted[target_col].shift(lag)
        
        # Features dérivées
        df_sorted['inflation_ma_3'] = df_sorted[target_col].rolling(window=3, min_periods=1).mean()
        df_sorted['inflation_ma_6'] = df_sorted[target_col].rolling(window=6, min_periods=1).mean()
        df_sorted['inflation_std_3'] = df_sorted[target_col].rolling(window=3, min_periods=1).std()
        df_sorted['inflation_trend'] = df_sorted[target_col].diff()
        
        # Saisonnalité
        df_sorted['mois_sin'] = np.sin(2 * np.pi * df_sorted['mois'] / 12)
        df_sorted['mois_cos'] = np.cos(2 * np.pi * df_sorted['mois'] / 12)
        
        # Mise à jour des features
        lag_cols = [f"lag_{i}" for i in range(1, max_lag + 1)]
        derived_cols = ['inflation_ma_3', 'inflation_ma_6', 'inflation_std_3', 
                       'inflation_trend', 'mois_sin', 'mois_cos']
        self.all_features = self.feature_cols + lag_cols + derived_cols
        
        return df_sorted
    
    def calculate_feature_correlations(self, df):
        """Calcule les corrélations avec validation statistique"""
        logger.info("📊 Calcul des corrélations")
        
        correlations = {}
        target_data = df["inflation_mom"].dropna()
        
        for feature in self.all_features:
            if feature in df.columns:
                feature_data = df[feature]
                aligned_data = pd.concat([target_data, feature_data], axis=1).dropna()
                
                if len(aligned_data) > 15:  # Seuil plus strict
                    corr = aligned_data.corr().iloc[0, 1]
                    correlations[feature] = abs(corr) if not np.isnan(corr) else 0
                else:
                    correlations[feature] = 0
        
        self.feature_correlations = correlations
        return correlations
    
    def preprocess_data(self, df):
        """Préprocessing optimisé avec gestion des outliers"""
        logger.info("🧹 Préprocessing des données")
        
        # Gestion des valeurs manquantes
        for col in self.all_features:
            if col in df.columns:
                if col.startswith("lag_") or col.startswith("inflation_"):
                    df[col] = df[col].fillna(method='ffill').fillna(method='bfill').fillna(0.0)
                else:
                    # Gestion des outliers
                    Q1 = df[col].quantile(0.25)
                    Q3 = df[col].quantile(0.75)
                    IQR = Q3 - Q1
                    lower_bound = Q1 - 1.5 * IQR
                    upper_bound = Q3 + 1.5 * IQR
                    df[col] = df[col].clip(lower=lower_bound, upper=upper_bound)
                    df[col] = df[col].fillna(df[col].median())
        
        # Division train/test
        train_mask = (df["annee"] < 2025) | ((df["annee"] == 2025) & (df["mois"] < 4))
        train_df = df[train_mask].dropna(subset=["inflation_mom"])
        
        logger.info(f"🏋️ Données d'entraînement: {len(train_df)} observations")
        return train_df, df
    
    def build_and_train_model(self, train_df):
        """Entraîne le modèle avec validation croisée"""
        logger.info("🌲 Entraînement du modèle Random Forest")
        
        X = train_df[self.all_features]
        y = train_df["inflation_mom"]
        
        # Normalisation
        X_scaled = self.scaler.fit_transform(X)
        
        # Modèle Random Forest optimisé
        self.model = RandomForestRegressor(
            n_estimators=150,
            max_depth=12,
            min_samples_split=5,
            min_samples_leaf=2,
            max_features='sqrt',
            bootstrap=True,
            random_state=42,
            n_jobs=-1
        )
        
        # Validation croisée
        cv_scores = cross_val_score(self.model, X_scaled, y, cv=5, scoring='neg_mean_squared_error')
        cv_rmse = np.sqrt(-cv_scores.mean())
        
        # Entraînement final
        self.model.fit(X_scaled, y)
        
        # Évaluation complète
        predictions = self.model.predict(X_scaled)
        rmse = np.sqrt(mean_squared_error(y, predictions))
        mae = mean_absolute_error(y, predictions)
        r2 = r2_score(y, predictions)
        
        # Métriques
        self.model_metrics = {
            'rmse': rmse,
            'mae': mae,
            'r2': r2,
            'cv_rmse': cv_rmse
        }
        
        # Importance des variables
        self.feature_importance = dict(zip(self.all_features, self.model.feature_importances_))
        
        logger.info(f"📈 Performance - RMSE: {rmse:.6f}, MAE: {mae:.6f}, R²: {r2:.6f}")
        logger.info(f"📊 CV-RMSE: {cv_rmse:.6f}")
        
        # Sauvegarde
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'features': self.all_features,
            'metrics': self.model_metrics
        }
        joblib.dump(model_data, self.model_path)
        logger.info("💾 Modèle sauvegardé")
    
    def predict_inflation(self, df, start_month=4, end_month=9):
        """Prédictions avec intervalles de confiance"""
        logger.info(f"🔮 Prédictions pour 2025-{start_month:02d} à 2025-{end_month:02d}")
        
        predictions = []
        confidence_intervals = []
        
        for month in range(start_month, end_month + 1):
            mask = (df["annee"] == 2025) & (df["mois"] == month)
            idx = df[mask].index
            
            if len(idx) == 0:
                continue
            
            idx = idx[0]
            
            # Préparer les features
            X_pred = df.loc[[idx], self.all_features].fillna(0.0)
            X_pred_scaled = self.scaler.transform(X_pred)
            
            # Prédiction avec intervalle de confiance
            pred_value = self.model.predict(X_pred_scaled)[0]
            
            # Estimation de l'incertitude (approximation)
            estimator_predictions = [estimator.predict(X_pred_scaled)[0] 
                                   for estimator in self.model.estimators_]
            std_pred = np.std(estimator_predictions)
            ci_lower = pred_value - 1.96 * std_pred
            ci_upper = pred_value + 1.96 * std_pred
            
            predictions.append((2025, month, pred_value))
            confidence_intervals.append((ci_lower, ci_upper))
            
            # Mettre à jour pour la prochaine prédiction
            df.at[idx, "inflation_mom"] = pred_value
            
            # Recalculer les features dépendantes
            self._update_derived_features(df, idx)
            
            logger.info(f"📅 2025-{month:02d}: {pred_value:.6f} [{ci_lower:.6f}, {ci_upper:.6f}]")
        
        return predictions, confidence_intervals
    
    def _update_derived_features(self, df, idx):
        """Met à jour les features dérivées après prédiction"""
        # Recalculer les lags
        for lag in range(1, 7):
            if f"lag_{lag}" in df.columns:
                df[f"lag_{lag}"] = df["inflation_mom"].shift(lag).fillna(0.0)
        
        # Recalculer les moyennes mobiles
        if 'inflation_ma_3' in df.columns:
            df['inflation_ma_3'] = df["inflation_mom"].rolling(window=3, min_periods=1).mean()
        if 'inflation_ma_6' in df.columns:
            df['inflation_ma_6'] = df["inflation_mom"].rolling(window=6, min_periods=1).mean()
        if 'inflation_std_3' in df.columns:
            df['inflation_std_3'] = df["inflation_mom"].rolling(window=3, min_periods=1).std()
        if 'inflation_trend' in df.columns:
            df['inflation_trend'] = df["inflation_mom"].diff()
    
    def display_feature_ranking(self):
        """Affiche le classement des variables avec métriques"""
        logger.info("📋 Analyse des variables")
        
        print("\n" + "="*90)
        print("🏆 PERFORMANCE DU MODÈLE")
        print("="*90)
        print(f"RMSE: {self.model_metrics['rmse']:.6f}")
        print(f"MAE:  {self.model_metrics['mae']:.6f}")
        print(f"R²:   {self.model_metrics['r2']:.6f}")
        print(f"CV-RMSE: {self.model_metrics['cv_rmse']:.6f}")
        
        print("\n" + "="*90)
        print("🏆 TOP 15 VARIABLES PAR IMPORTANCE")
        print("="*90)
        
        rf_ranking = sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)
        
        print(f"{'Rang':<5} | {'Variable':<25} | {'Importance':<12} | {'Corrélation':<12}")
        print("-"*90)
        
        for rank, (feature, importance) in enumerate(rf_ranking[:15], 1):
            correlation = self.feature_correlations.get(feature, 0)
            print(f"{rank:<5} | {feature:<25} | {importance:<12.6f} | {correlation:<12.6f}")
        
        print("="*90)
    
    def plot_enhanced_results(self, df, predictions, confidence_intervals=None):
        """Visualisation améliorée des résultats"""
        logger.info("📊 Génération des graphiques")
        
        plt.style.use('seaborn-v0_8')
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        
        # Graphique principal avec intervalles de confiance
        ax1 = axes[0, 0]
        recent_data = df[df["annee"] >= 2020].sort_values(["annee", "mois"])
        dates = pd.to_datetime(recent_data["annee"].astype(str) + "-" + recent_data["mois"].astype(str))
        
        ax1.plot(dates, recent_data["inflation_mom"], 'b-', label="Inflation historique", linewidth=2)
        
        if predictions:
            pred_dates = pd.to_datetime([f"{y}-{m}" for y, m, _ in predictions])
            pred_values = [p for _, _, p in predictions]
            ax1.plot(pred_dates, pred_values, 'r--', marker='o', label="Prédictions RF", linewidth=2, markersize=6)
            
            # Intervalles de confiance
            if confidence_intervals:
                ci_lower = [ci[0] for ci in confidence_intervals]
                ci_upper = [ci[1] for ci in confidence_intervals]
                ax1.fill_between(pred_dates, ci_lower, ci_upper, alpha=0.3, color='red', label="IC 95%")
        
        ax1.set_title("Inflation Mensuelle - Historique et Prédictions", fontsize=14, fontweight='bold')
        ax1.set_xlabel("Date")
        ax1.set_ylabel("Inflation (%)")
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Importance des variables
        ax2 = axes[0, 1]
        top_features = sorted(self.feature_importance.items(), key=lambda x: x[1], reverse=True)[:12]
        features, importances = zip(*top_features)
        bars = ax2.barh(range(len(features)), importances, color='skyblue')
        ax2.set_yticks(range(len(features)))
        ax2.set_yticklabels(features)
        ax2.set_title("Importance des Variables", fontsize=14, fontweight='bold')
        ax2.set_xlabel("Importance")
        
        # Corrélations
        ax3 = axes[1, 0]
        top_corr = sorted(self.feature_correlations.items(), key=lambda x: x[1], reverse=True)[:12]
        features_corr, correlations = zip(*top_corr)
        ax3.barh(range(len(features_corr)), correlations, color='lightgreen')
        ax3.set_yticks(range(len(features_corr)))
        ax3.set_yticklabels(features_corr)
        ax3.set_title("Corrélations avec l'Inflation", fontsize=14, fontweight='bold')
        ax3.set_xlabel("Corrélation Absolue")
        
        # Métriques de performance
        ax4 = axes[1, 1]
        metrics = ['RMSE', 'MAE', 'R²', 'CV-RMSE']
        values = [self.model_metrics['rmse'], self.model_metrics['mae'], 
                 self.model_metrics['r2'], self.model_metrics['cv_rmse']]
        colors = ['red', 'orange', 'green', 'purple']
        
        bars = ax4.bar(metrics, values, color=colors, alpha=0.7)
        ax4.set_title("Métriques de Performance", fontsize=14, fontweight='bold')
        ax4.set_ylabel("Valeur")
        
        # Ajouter les valeurs sur les barres
        for bar, value in zip(bars, values):
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.001, 
                    f'{value:.4f}', ha='center', va='bottom')
        
        plt.tight_layout()
        plt.show()

        st.pyplot(plt.gcf())  # Affiche la figure active dans Streamlit
        plt.close()

    def run_pipeline(self, parquet_path, nb_mois=6):
        """Pipeline complet avec gestion d'erreurs robuste"""
        try:
            start_month = 4
            end_month = min(start_month + nb_mois - 1, 12)
            
            # Étapes du pipeline
            self.load_and_prepare_data(parquet_path)
            df_with_features = self.add_lag_features()
            
            # Créer les périodes futures
            last_data = df_with_features[df_with_features["inflation_mom"].notna()].iloc[-1]
            future_rows = []
            for month in range(start_month, end_month + 1):
                row = last_data.copy()
                row["annee"] = 2025
                row["mois"] = month
                row["inflation_mom"] = np.nan
                future_rows.append(row)
            
            future_df = pd.DataFrame(future_rows)
            full_df = pd.concat([df_with_features, future_df], ignore_index=True)
            
            # Preprocessing et entraînement
            train_df, full_df = self.preprocess_data(full_df)
            self.calculate_feature_correlations(train_df)
            self.build_and_train_model(train_df)
            
            # Prédictions
            predictions, confidence_intervals = self.predict_inflation(full_df, start_month, end_month)
            
            # Affichage des résultats
            self.display_feature_ranking()
            self.plot_enhanced_results(full_df, predictions, confidence_intervals)
            
            logger.info("🎉 Pipeline terminé avec succès!")
            
            # Créer DataFrame des résultats
            result_df = pd.DataFrame(predictions, columns=["annee", "mois", "inflation_pred"])
            if confidence_intervals:
                result_df["ci_lower"] = [ci[0] for ci in confidence_intervals]
                result_df["ci_upper"] = [ci[1] for ci in confidence_intervals]
            
            return result_df
            
        except Exception as e:
            logger.error(f"❌ Erreur dans le pipeline: {e}")
            raise

def run_prediction(parquet_path, nb_mois=6):
    """Fonction principale simplifiée"""
    predictor = InflationRFPredictor()
    return predictor.run_pipeline(parquet_path, nb_mois)

def run_random_forest(nb_mois: int = 6) -> pd.DataFrame:
    parquet_path = str(DATA_DIR / "fichierpred.parquet")
    predictor = InflationRFPredictor()

    start_month = 4
    end_month = start_month + nb_mois - 1
    if end_month > 12:
        raise ValueError("Le nombre de mois à prédire dépasse décembre 2025 (mois > 12)")

    # Run complet : data, train, prédiction, affichage graphique
    predictions_df = predictor.run_pipeline(parquet_path, nb_mois=nb_mois)

    # Préparer DataFrame final avec colonne Date
    if predictions_df is not None and not predictions_df.empty:
        df_pred = predictions_df.copy()
        df_pred["Date"] = pd.to_datetime(df_pred["annee"].astype(str) + "-" + df_pred["mois"].astype(str) + "-01").dt.date

        return df_pred[["Date", "inflation_pred"]]
    
    # Si échec ou pas de données
    return pd.DataFrame()


# Usage
if __name__ == "__main__":  
    try:
        nb_mois = int(input("📅 Combien de mois souhaitez-vous prédire (entre 1 et 9) ? "))
        if nb_mois < 1 or nb_mois > 9:
            raise ValueError("Veuillez choisir un nombre entre 1 et 9.")
    except ValueError as e:
        print(f"❌ Erreur: {e}")
        exit()

    df_predictions = run_random_forest(nb_mois=nb_mois)
    print(df_predictions)

