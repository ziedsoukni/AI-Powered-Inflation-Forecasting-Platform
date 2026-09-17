import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import logging
from typing import List, Tuple, Optional
from datetime import datetime
import warnings
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import joblib
import os
import streamlit as st
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InflationPredictor:
    def __init__(self):
        """Initialize predictor without Spark"""
        self.model = None
        self.feature_cols = []
        self.all_features = []
        self.model_path = "models/inflation_model.pkl"
        self.data_quality_report = {}
        
        # Create models directory if not exists
        os.makedirs("models", exist_ok=True)
    
    def validate_data_quality(self, df) -> bool:
        """Comprehensive data quality validation"""
        logger.info("🔍 Validation de la qualité des données")
        
        # Basic checks
        if df.empty:
            raise ValueError("Dataset is empty")
        
        # Check for required columns
        required_cols = ["inflation_mom", "annee", "mois"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Data quality metrics
        total_rows = len(df)
        null_counts = df.isnull().sum()
        
        self.data_quality_report = {
            "total_rows": total_rows,
            "null_percentages": {col: (null_counts[col] / total_rows) * 100 for col in df.columns},
            "numeric_cols": len(self.feature_cols)
        }
        
        # Check for excessive nulls
        high_null_cols = [col for col, pct in self.data_quality_report["null_percentages"].items() 
                         if pct > 50 and col in self.feature_cols]
        if high_null_cols:
            logger.warning(f"⚠️ Columns with >50% nulls: {high_null_cols}")
        
        # Check date range validity
        avg_year = df["annee"].mean()
        avg_month = df["mois"].mean()
        
        if avg_year < 2000 or avg_year > 2030:
            logger.warning(f"⚠️ Unusual year range detected: avg={avg_year}")
        
        logger.info(f"✅ Data quality: {total_rows} rows, {len(self.feature_cols)} features")
        return True
    
    def load_and_prepare_data(self, parquet_path: str) -> None:
        """Load and prepare data with validation"""
        try:
            logger.info(f"📥 Chargement des données depuis {parquet_path}")
            self.df = pd.read_parquet(parquet_path)
            
            # Identify numeric features
            exclude_cols = ["inflation_mom", "annee", "mois"]
            self.feature_cols = []
            
            for col_name in self.df.columns:
                if (col_name not in exclude_cols and 
                    pd.api.types.is_numeric_dtype(self.df[col_name])):
                    self.feature_cols.append(col_name)
            
            # Validate data quality
            self.validate_data_quality(self.df)
            
            logger.info(f"✅ Données préparées: {len(self.df)} lignes, {len(self.feature_cols)} features")
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement: {e}")
            raise
    
    def add_lag_features(self, target_col: str = "inflation_mom", max_lag: int = 12) -> pd.DataFrame:
        """Add lag features with validation"""
        logger.info(f"🕰️ Ajout des lags (1 à {max_lag}) pour {target_col}")
        
        # Sort by date
        df_pandas = self.df.sort_values(["annee", "mois"]).reset_index(drop=True)
        
        # Validate time series continuity
        df_pandas['date'] = pd.to_datetime(df_pandas['annee'].astype(str) + '-' + df_pandas['mois'].astype(str))
        date_gaps = df_pandas['date'].diff().dt.days
        large_gaps = date_gaps[date_gaps > 40]  # More than ~1 month
        
        if len(large_gaps) > 0:
            logger.warning(f"⚠️ Detected {len(large_gaps)} potential time gaps in data")
        
        # Add lag features
        for lag in range(1, max_lag + 1):
            df_pandas[f"lag_{lag}"] = df_pandas[target_col].shift(lag)
        
        # Validate lag creation
        lag_cols = [f"lag_{i}" for i in range(1, max_lag + 1)]
        self.all_features = self.feature_cols + lag_cols
        
        # Check for sufficient historical data
        valid_rows = df_pandas.dropna(subset=lag_cols[:3]).shape[0]  # Check first 3 lags
        if valid_rows < 50:
            logger.warning(f"⚠️ Only {valid_rows} rows with sufficient lag data")
        
        return df_pandas
    
    def create_future_periods(self, df_pandas: pd.DataFrame) -> pd.DataFrame:
        """Create future periods with validation"""
        logger.info("🔮 Création des périodes futures: 2025-04 à 2025-09")
        
        # Find the last valid observation
        last_valid_idx = df_pandas.dropna(subset=["inflation_mom"]).index[-1]
        last_row = df_pandas.loc[last_valid_idx].copy()
        
        # Validate last observation is reasonable
        if last_row["annee"] < 2020:
            logger.warning(f"⚠️ Last observation is from {last_row['annee']}, might be outdated")
        
        future_rows = []
        for month in range(4, 10):  # avril à septembre
            row = last_row.copy()
            row["annee"] = 2025
            row["mois"] = month
            row["inflation_mom"] = np.nan
            future_rows.append(row)
        
        future_df = pd.DataFrame(future_rows)
        full_df = pd.concat([df_pandas, future_df], ignore_index=True)
        
        return full_df.sort_values(["annee", "mois"]).reset_index(drop=True)
    
    def preprocess_data(self, df_pandas: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Enhanced preprocessing with outlier detection"""
        logger.info("🧹 Préprocessing des données")
        
        # Intelligent null handling
        for col_name in self.all_features:
            if col_name in df_pandas.columns:
                if col_name.startswith("lag_"):
                    # Use forward fill for lags, then 0
                    df_pandas[col_name] = df_pandas[col_name].fillna(method='ffill').fillna(0.0)
                else:
                    # Use median for other features
                    median_val = df_pandas[col_name].median()
                    df_pandas[col_name] = df_pandas[col_name].fillna(median_val if not pd.isna(median_val) else 0.0)
        
        # Outlier detection for target variable
        if "inflation_mom" in df_pandas.columns:
            Q1 = df_pandas["inflation_mom"].quantile(0.25)
            Q3 = df_pandas["inflation_mom"].quantile(0.75)
            IQR = Q3 - Q1
            outlier_mask = (df_pandas["inflation_mom"] < Q1 - 3*IQR) | (df_pandas["inflation_mom"] > Q3 + 3*IQR)
            outlier_count = outlier_mask.sum()
            
            if outlier_count > 0:
                logger.warning(f"⚠️ Detected {outlier_count} outliers in target variable")
        
        # Split data
        train_mask = (df_pandas["annee"] < 2025) | ((df_pandas["annee"] == 2025) & (df_pandas["mois"] < 4))
        future_mask = (df_pandas["annee"] == 2025) & (df_pandas["mois"] >= 4) & (df_pandas["mois"] <= 9)
        
        train_df = df_pandas[train_mask].copy()
        future_df = df_pandas[future_mask].copy()
        
        # Remove rows with NaN target
        initial_train_size = len(train_df)
        train_df = train_df.dropna(subset=["inflation_mom"])
        final_train_size = len(train_df)
        
        if initial_train_size - final_train_size > 0:
            logger.info(f"📊 Removed {initial_train_size - final_train_size} rows with missing target")
        
        # Validate sufficient training data
        if len(train_df) < 100:
            logger.warning(f"⚠️ Only {len(train_df)} training samples available")
        
        logger.info(f"🏋️ Training: {len(train_df)} observations, Future: {len(future_df)} observations")
        
        return train_df, future_df
    
    def build_and_train_model(self, train_df: pd.DataFrame) -> None:
        """Build and train model with enhanced validation"""
        logger.info("🚧 Construction et entraînement du modèle")
        
        # Prepare data
        X = train_df[self.all_features]
        y = train_df["inflation_mom"]
        
        # Create pipeline
        pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('gbt', GradientBoostingRegressor(random_state=42))
        ])
        
        # Parameter grid
        param_grid = {
            'gbt__n_estimators': [50, 100, 150],
            'gbt__max_depth': [3, 5, 7],
            'gbt__learning_rate': [0.05, 0.1, 0.2],
            'gbt__subsample': [0.8, 1.0]
        }
        
        # Grid search with cross-validation
        grid_search = GridSearchCV(
            estimator=pipeline,
            param_grid=param_grid,
            cv=3,
            scoring='neg_mean_squared_error',
            n_jobs=-1,
            verbose=1
        )
        
        logger.info("⏳ Entraînement avec validation croisée...")
        start_time = datetime.now()
        grid_search.fit(X, y)
        self.model = grid_search.best_estimator_
        training_time = (datetime.now() - start_time).total_seconds()
        
        # Model evaluation
        predictions = self.model.predict(X)
        rmse = np.sqrt(mean_squared_error(y, predictions))
        mae = mean_absolute_error(y, predictions)
        r2 = r2_score(y, predictions)
        
        logger.info(f"📈 Model Performance:")
        logger.info(f"   RMSE: {rmse:.6f}")
        logger.info(f"   MAE: {mae:.6f}")
        logger.info(f"   R²: {r2:.6f}")
        logger.info(f"   Training time: {training_time:.2f}s")
        logger.info(f"   Best params: {grid_search.best_params_}")
        
        # Save model
        self.save_model()
    
    def save_model(self) -> None:
        """Save model with error handling"""
        try:
            logger.info(f"💾 Sauvegarde du modèle vers {self.model_path}")
            joblib.dump(self.model, self.model_path)
            logger.info("✅ Modèle sauvegardé avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur lors de la sauvegarde: {e}")
            raise
    
    def load_model(self) -> None:
        """Load model with validation"""
        try:
            logger.info(f"📂 Chargement du modèle depuis {self.model_path}")
            self.model = joblib.load(self.model_path)
            logger.info("✅ Modèle chargé avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement: {e}")
            raise
    
    def predict_iteratively(self, full_df: pd.DataFrame) -> List[Tuple[int, int, float]]:
        """Enhanced iterative prediction with validation"""
        logger.info("🔄 Prédictions itératives pour avril-septembre 2025")
        predictions = []
        
        for month in range(4, 10):
            mask = (full_df["annee"] == 2025) & (full_df["mois"] == month)
            indices = full_df[mask].index
            
            if len(indices) == 0:
                logger.warning(f"⚠️ Pas de données pour 2025-{month}")
                break
            
            idx = indices[0]
            
            # Validate features exist
            missing_features = [f for f in self.all_features if f not in full_df.columns]
            if missing_features:
                logger.error(f"❌ Missing features: {missing_features}")
                break
            
            row_features = full_df.loc[[idx], self.all_features]
            row_features = row_features.fillna(0.0)
            
            # Validate feature values
            if row_features.isnull().any().any():
                logger.warning(f"⚠️ NaN values detected in features for 2025-{month}")
            
            try:
                predicted_value = self.model.predict(row_features)[0]
                
                # Validate prediction
                if np.isnan(predicted_value) or np.isinf(predicted_value):
                    logger.error(f"❌ Invalid prediction for 2025-{month}: {predicted_value}")
                    break
                
                predictions.append((2025, month, predicted_value))
                full_df.at[idx, "inflation_mom"] = predicted_value
                
                # Update lags efficiently
                for lag in range(1, 13):
                    if f"lag_{lag}" in full_df.columns:
                        full_df[f"lag_{lag}"] = full_df["inflation_mom"].shift(lag).fillna(0.0)
                
                logger.info(f"📅 Prédiction pour 2025-{month:02d}: {predicted_value:.6f}")
                
            except Exception as e:
                logger.error(f"❌ Erreur lors de la prédiction pour 2025-{month}: {e}")
                break
        
        # Display results
        self._display_predictions(predictions)
        return predictions
    
    def _display_predictions(self, predictions: List[Tuple[int, int, float]]) -> None:
        """Display predictions in formatted table"""
        print("\n✨ Prédictions d'inflation mensuelle (avril-septembre 2025) ✨")
        print("=" * 60)
        print(f"{'Date':<12} | {'Prédiction':>12} | {'Variation':>12}")
        print("-" * 60)
        
        for i, (y, m, pred) in enumerate(predictions):
            if i > 0:
                prev_pred = predictions[i-1][2]
                variation = pred - prev_pred
                var_str = f"{variation:+.6f}"
            else:
                var_str = "N/A"
            
            print(f"{y}-{m:02d}      | {pred:12.6f} | {var_str:>12}")
        
        print("=" * 60)
        
        if predictions:
            avg_pred = np.mean([p[2] for p in predictions])
            print(f"Moyenne prédite: {avg_pred:.6f}")
    
    def plot_results(self, full_df: pd.DataFrame, predictions: List[Tuple[int, int, float]]) -> None:
        """Enhanced visualization"""
        logger.info("📊 Génération des graphiques")
        
        full_df = full_df.sort_values(["annee", "mois"]).reset_index(drop=True)
        dates = pd.to_datetime(full_df["annee"].astype(str) + "-" + full_df["mois"].astype(str))
        
        # Filter recent data for better visualization
        recent_mask = dates >= '2020-01-01'
        recent_dates = dates[recent_mask]
        recent_values = full_df["inflation_mom"][recent_mask]
        
        plt.figure(figsize=(14, 8))
        
        # Plot historical data
        plt.subplot(2, 1, 1)
        plt.plot(recent_dates, recent_values, label="Inflation réelle", marker='o', alpha=0.7, linewidth=2)
        
        # Plot predictions
        pred_dates = pd.to_datetime([f"{y}-{m}" for y, m, _ in predictions])
        pred_values = [p for _, _, p in predictions]
        plt.plot(pred_dates, pred_values, label="Inflation prédite", marker='X', 
                linestyle='--', color='red', linewidth=3, markersize=10)
        
        plt.title("Inflation mensuelle - Historique et Prédictions", fontsize=14, fontweight='bold')
        plt.xlabel("Date")
        plt.ylabel("Inflation mensuelle (%)")
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        # Statistics subplot
        plt.subplot(2, 1, 2)
        if predictions:
            months = [f"{y}-{m:02d}" for y, m, _ in predictions]
            values = [p for _, _, p in predictions]
            plt.bar(months, values, color='skyblue', alpha=0.7)
            plt.title("Prédictions détaillées par mois", fontsize=12)
            plt.ylabel("Inflation (%)")
            plt.xticks(rotation=45)
            plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.show()

        st.pyplot(plt.gcf())  # Affiche la figure active dans Streamlit
        plt.close()

    
    def run_full_pipeline(self, parquet_path: str) -> List[Tuple[int, int, float]]:
        """Execute complete pipeline with comprehensive error handling"""
        try:
            start_time = datetime.now()
            
            self.load_and_prepare_data(parquet_path)
            df_pandas = self.add_lag_features()
            df_pandas = self.create_future_periods(df_pandas)
            train_df, future_df = self.preprocess_data(df_pandas)
            self.build_and_train_model(train_df)
            predictions = self.predict_iteratively(df_pandas)
            self.plot_results(df_pandas, predictions)
            
            total_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"🎉 Pipeline complet terminé en {total_time:.2f}s")
            
            return predictions
            
        except Exception as e:
            logger.error(f"❌ Erreur dans le pipeline: {e}")
            raise
    
    def run_prediction_only(self, parquet_path: str) -> List[Tuple[int, int, float]]:
        """Run predictions only with pre-trained model"""
        try:
            start_time = datetime.now()
            
            self.load_model()
            self.load_and_prepare_data(parquet_path)
            df_pandas = self.add_lag_features()
            df_pandas = self.create_future_periods(df_pandas)
            train_df, future_df = self.preprocess_data(df_pandas)
            predictions = self.predict_iteratively(df_pandas)
            self.plot_results(df_pandas, predictions)
            
            total_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"🎉 Prédictions terminées en {total_time:.2f}s")
            
            return predictions
            
        except Exception as e:
            logger.error(f"❌ Erreur lors des prédictions: {e}")
            raise
        
def run_gradient_boosting() -> pd.DataFrame:
    parquet_path = r"C:\Users\user\Desktop\streamlit\data\fichierpred.parquet"
    predictor = InflationPredictor()
    predictions = predictor.run_full_pipeline(parquet_path)

    if predictions:
        df_pred = pd.DataFrame(predictions, columns=["annee", "mois", "inflation_pred"])
        df_pred["Date"] = pd.to_datetime(df_pred["annee"].astype(str) + "-" + df_pred["mois"].astype(str) + "-01")
        return df_pred[["Date", "inflation_pred"]]
    return pd.DataFrame()

# Usage
if __name__ == "__main__":  
    parquet_path = "C:/Users/user/Desktop/streamlit/data/fichierpred.parquet"
    predictor = InflationPredictor()

    # Full pipeline (train + predict)
    predictions = predictor.run_full_pipeline(parquet_path)

    # Or prediction only (with pre-trained model)
    # predictions = predictor.run_prediction_only(parquet_path)


    
