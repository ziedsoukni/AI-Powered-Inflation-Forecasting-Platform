import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import logging
from typing import List, Tuple, Optional, Dict
from datetime import datetime
import warnings
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.feature_selection import SelectKBest, f_regression, mutual_info_regression
from sklearn.inspection import permutation_importance
import joblib
import os
import streamlit as st
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InflationPredictor:
    def __init__(self):
        """Initialize predictor with feature selection capabilities"""
        self.model = None
        self.feature_cols = []
        self.all_features = []
        self.selected_features = []
        self.feature_importance_scores = {}
        self.feature_selector = None
        self.model_path = "models/inflation_model.pkl"
        self.feature_selector_path = "models/feature_selector.pkl"
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

    def create_future_periods(self, df_pandas: pd.DataFrame, start_month: int = 4, end_month: int = 12) -> pd.DataFrame:
        """Create future periods with validation"""
        logger.info(f"🔮 Création des périodes futures: 2025-{start_month} à 2025-{end_month}")
        
        last_valid_idx = df_pandas.dropna(subset=["inflation_mom"]).index[-1]
        last_row = df_pandas.loc[last_valid_idx].copy()
        
        if last_row["annee"] < 2020:
            logger.warning(f"⚠️ Last observation is from {last_row['annee']}, might be outdated")
        
        future_rows = []
        for month in range(start_month, end_month + 1):
            row = last_row.copy()
            row["annee"] = 2025
            row["mois"] = month
            row["inflation_mom"] = np.nan
            future_rows.append(row)
        
        future_df = pd.DataFrame(future_rows)
        full_df = pd.concat([df_pandas, future_df], ignore_index=True)
        return full_df.sort_values(["annee", "mois"]).reset_index(drop=True)

    def calculate_feature_importance(self, X: pd.DataFrame, y: pd.Series) -> Dict[str, float]:
        """Calculate feature importance using multiple methods"""
        logger.info("📊 Calcul de l'importance des features")
        
        importance_scores = {}
        
        # 1. Correlation with target
        logger.info("   📈 Calcul des corrélations...")
        correlations = X.corrwith(y).abs()
        importance_scores['correlation'] = correlations.to_dict()
        
        # 2. F-score (univariate feature selection)
        logger.info("   📊 Calcul des F-scores...")
        f_scores, _ = f_regression(X.fillna(0), y)
        importance_scores['f_score'] = dict(zip(X.columns, f_scores))
        
        # 3. Mutual information
        logger.info("   🔄 Calcul de l'information mutuelle...")
        try:
            mi_scores = mutual_info_regression(X.fillna(0), y, random_state=42)
            importance_scores['mutual_info'] = dict(zip(X.columns, mi_scores))
        except Exception as e:
            logger.warning(f"⚠️ Erreur mutual info: {e}")
            importance_scores['mutual_info'] = {col: 0 for col in X.columns}
        
        # 4. Gradient Boosting built-in importance
        logger.info("   🌳 Calcul de l'importance GBT...")
        temp_model = GradientBoostingRegressor(n_estimators=50, random_state=42)
        temp_model.fit(X.fillna(0), y)
        importance_scores['gbt_importance'] = dict(zip(X.columns, temp_model.feature_importances_))
        
        return importance_scores
    
    def select_features_by_importance(self, X: pd.DataFrame, y: pd.Series, 
                                    selection_method: str = 'combined',
                                    top_k: int = 20) -> List[str]:
        """Select features based on importance scores"""
        logger.info(f"🎯 Sélection des {top_k} meilleures features par méthode '{selection_method}'")
        
        # Calculate importance scores
        importance_scores = self.calculate_feature_importance(X, y)
        self.feature_importance_scores = importance_scores
        
        if selection_method == 'combined':
            # Combine multiple importance measures
            combined_scores = {}
            for feature in X.columns:
                # Normalize each score to 0-1 range
                corr_score = importance_scores['correlation'].get(feature, 0)
                f_score = importance_scores['f_score'].get(feature, 0)
                mi_score = importance_scores['mutual_info'].get(feature, 0)
                gbt_score = importance_scores['gbt_importance'].get(feature, 0)
                
                # Normalize scores
                max_f = max(importance_scores['f_score'].values()) if importance_scores['f_score'].values() else 1
                max_mi = max(importance_scores['mutual_info'].values()) if importance_scores['mutual_info'].values() else 1
                max_gbt = max(importance_scores['gbt_importance'].values()) if importance_scores['gbt_importance'].values() else 1
                
                normalized_f = f_score / max_f if max_f > 0 else 0
                normalized_mi = mi_score / max_mi if max_mi > 0 else 0
                normalized_gbt = gbt_score / max_gbt if max_gbt > 0 else 0
                
                # Combined score (weighted average)
                combined_scores[feature] = (
                    0.25 * corr_score +
                    0.25 * normalized_f +
                    0.25 * normalized_mi +
                    0.25 * normalized_gbt
                )
            
            # Sort by combined score
            sorted_features = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
            
        elif selection_method == 'correlation':
            sorted_features = sorted(importance_scores['correlation'].items(), key=lambda x: x[1], reverse=True)
        elif selection_method == 'f_score':
            sorted_features = sorted(importance_scores['f_score'].items(), key=lambda x: x[1], reverse=True)
        elif selection_method == 'mutual_info':
            sorted_features = sorted(importance_scores['mutual_info'].items(), key=lambda x: x[1], reverse=True)
        elif selection_method == 'gbt_importance':
            sorted_features = sorted(importance_scores['gbt_importance'].items(), key=lambda x: x[1], reverse=True)
        else:
            raise ValueError(f"Unknown selection method: {selection_method}")
        
        # Select top K features
        selected_features = [feat for feat, score in sorted_features[:top_k]]
        
        # Always include some lag features if they exist
        lag_features = [f for f in selected_features if f.startswith('lag_')]
        if len(lag_features) < 3:
            additional_lags = [f for f in X.columns if f.startswith('lag_') and f not in selected_features][:3-len(lag_features)]
            selected_features.extend(additional_lags)
        
        # Remove duplicates and limit to top_k
        selected_features = list(dict.fromkeys(selected_features))[:top_k]
        
        logger.info(f"✅ Features sélectionnées: {len(selected_features)}")
        for i, feature in enumerate(selected_features[:10]):  # Show top 10
            score = sorted_features[i][1] if i < len(sorted_features) else 0
            logger.info(f"   {i+1:2d}. {feature:<20} (score: {score:.4f})")
        
        return selected_features
    
    def plot_feature_importance(self, top_n: int = 15) -> None:
        """Plot feature importance visualization"""
        if not self.feature_importance_scores or not self.selected_features:
            logger.warning("⚠️ No feature importance data available")
            return
        
        logger.info("📊 Génération du graphique d'importance des features")
        
        # Get top features and their combined scores
        feature_scores = []
        for feature in self.selected_features[:top_n]:
            if feature in self.feature_importance_scores.get('correlation', {}):
                corr_score = self.feature_importance_scores['correlation'][feature]
                f_score = self.feature_importance_scores['f_score'][feature]
                mi_score = self.feature_importance_scores['mutual_info'][feature]
                gbt_score = self.feature_importance_scores['gbt_importance'][feature]
                
                # Normalize and combine
                max_f = max(self.feature_importance_scores['f_score'].values()) if self.feature_importance_scores['f_score'].values() else 1
                max_mi = max(self.feature_importance_scores['mutual_info'].values()) if self.feature_importance_scores['mutual_info'].values() else 1
                max_gbt = max(self.feature_importance_scores['gbt_importance'].values()) if self.feature_importance_scores['gbt_importance'].values() else 1
                
                combined_score = (
                    0.25 * corr_score +
                    0.25 * (f_score / max_f if max_f > 0 else 0) +
                    0.25 * (mi_score / max_mi if max_mi > 0 else 0) +
                    0.25 * (gbt_score / max_gbt if max_gbt > 0 else 0)
                )
                
                feature_scores.append((feature, combined_score))
        
        if not feature_scores:
            return
        
        # Sort by score
        feature_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Create plot
        plt.figure(figsize=(12, 8))
        features, scores = zip(*feature_scores)
        
        # Create horizontal bar plot
        y_pos = np.arange(len(features))
        bars = plt.barh(y_pos, scores, color='skyblue', alpha=0.7)
        
        # Customize plot
        plt.yticks(y_pos, features)
        plt.xlabel('Score d\'importance combiné')
        plt.title(f'Top {len(features)} Features par Importance', fontsize=14, fontweight='bold')
        plt.grid(axis='x', alpha=0.3)
        
        # Add value labels on bars
        for i, (bar, score) in enumerate(zip(bars, scores)):
            plt.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height()/2, 
                    f'{score:.3f}', va='center', ha='left', fontsize=9)
        
        plt.tight_layout()
        
        # Show in streamlit if available
        try:
            st.pyplot(plt.gcf())
        except:
            plt.show()
        
        plt.close()
    
    def preprocess_data(self, df_pandas: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Enhanced preprocessing with feature selection"""
        logger.info("🧹 Préprocessing des données avec sélection de features")
        
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
        
        # Feature selection on training data
        if len(train_df) > 0:
            X_train = train_df[self.all_features]
            y_train = train_df["inflation_mom"]
            
            # Select features by importance
            self.selected_features = self.select_features_by_importance(
                X_train, y_train, 
                selection_method='combined',
                top_k=min(20, len(self.all_features))
            )
            
            # Plot feature importance
            self.plot_feature_importance()
        
        # Validate sufficient training data
        if len(train_df) < 100:
            logger.warning(f"⚠️ Only {len(train_df)} training samples available")
        
        logger.info(f"🏋️ Training: {len(train_df)} observations, Future: {len(future_df)} observations")
        logger.info(f"🎯 Using {len(self.selected_features)} selected features")
        
        return train_df, future_df
    
    def build_and_train_model(self, train_df: pd.DataFrame) -> None:
        """Build and train model with selected features"""
        logger.info("🚧 Construction et entraînement du modèle avec features sélectionnées")
        
        # Use only selected features
        X = train_df[self.selected_features]
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
        
        # Calculate permutation importance on the trained model
        logger.info("🔍 Calcul de l'importance par permutation...")
        perm_importance = permutation_importance(
            self.model, X, y, 
            n_repeats=5, 
            random_state=42, 
            n_jobs=-1
        )
        
        # Store permutation importance
        self.feature_importance_scores['permutation'] = dict(
            zip(self.selected_features, perm_importance.importances_mean)
        )
        
        logger.info(f"📈 Model Performance:")
        logger.info(f"   RMSE: {rmse:.6f}")
        logger.info(f"   MAE: {mae:.6f}")
        logger.info(f"   R²: {r2:.6f}")
        logger.info(f"   Training time: {training_time:.2f}s")
        logger.info(f"   Best params: {grid_search.best_params_}")
        logger.info(f"   Features used: {len(self.selected_features)}")
        
        # Save model and feature info
        self.save_model()
    
    def save_model(self) -> None:
        """Save model and feature selection info"""
        try:
            logger.info(f"💾 Sauvegarde du modèle et des features vers {self.model_path}")
            
            # Save model
            joblib.dump(self.model, self.model_path)
            
            # Save feature selection info
            feature_info = {
                'selected_features': self.selected_features,
                'feature_importance_scores': self.feature_importance_scores,
                'all_features': self.all_features
            }
            joblib.dump(feature_info, self.feature_selector_path)
            
            logger.info("✅ Modèle et features sauvegardés avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur lors de la sauvegarde: {e}")
            raise
    
    def load_model(self) -> None:
        """Load model and feature selection info"""
        try:
            logger.info(f"📂 Chargement du modèle depuis {self.model_path}")
            self.model = joblib.load(self.model_path)
            
            # Load feature selection info
            if os.path.exists(self.feature_selector_path):
                feature_info = joblib.load(self.feature_selector_path)
                self.selected_features = feature_info.get('selected_features', [])
                self.feature_importance_scores = feature_info.get('feature_importance_scores', {})
                self.all_features = feature_info.get('all_features', [])
                logger.info(f"✅ Modèle chargé avec {len(self.selected_features)} features sélectionnées")
            else:
                logger.warning("⚠️ Fichier de sélection de features non trouvé")
                
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement: {e}")
            raise
    
    def predict_iteratively(self, full_df: pd.DataFrame, start_month: int = 4, end_month: int = 12) -> List[Tuple[int, int, float]]:
        logger.info(f"🔄 Prédictions itératives pour 2025-{start_month} à 2025-{end_month}")
        predictions = []
        
        for month in range(start_month, end_month + 1):
            mask = (full_df["annee"] == 2025) & (full_df["mois"] == month)
            indices = full_df[mask].index
            
            if len(indices) == 0:
                logger.warning(f"⚠️ Pas de données pour 2025-{month}")
                break
            
            idx = indices[0]
            
            # Use only selected features
            missing_features = [f for f in self.selected_features if f not in full_df.columns]
            if missing_features:
                logger.error(f"❌ Missing selected features: {missing_features}")
                break
            
            row_features = full_df.loc[[idx], self.selected_features]
            row_features = row_features.fillna(0.0)
            
            if row_features.isnull().any().any():
                logger.warning(f"⚠️ NaN values detected in features for 2025-{month}")
            
            try:
                predicted_value = self.model.predict(row_features)[0]
                if np.isnan(predicted_value) or np.isinf(predicted_value):
                    logger.error(f"❌ Invalid prediction for 2025-{month}: {predicted_value}")
                    break
                
                predictions.append((2025, month, predicted_value))
                full_df.at[idx, "inflation_mom"] = predicted_value
                
                # Update lag features
                for lag in range(1, 13):
                    if f"lag_{lag}" in full_df.columns:
                        full_df[f"lag_{lag}"] = full_df["inflation_mom"].shift(lag).fillna(0.0)
                
                logger.info(f"📅 Prédiction pour 2025-{month:02d}: {predicted_value:.6f}")
            except Exception as e:
                logger.error(f"❌ Erreur lors de la prédiction pour 2025-{month}: {e}")
                break
        
        self._display_predictions(predictions)
        return predictions
    
    def _display_predictions(self, predictions: List[Tuple[int, int, float]]) -> None:
        """Display predictions in formatted table"""
        print("\n✨ Prédictions d'inflation mensuelle (avec sélection de features) ✨")
        print("=" * 70)
        print(f"{'Date':<12} | {'Prédiction':>12} | {'Variation':>12}")
        print("-" * 70)
        
        for i, (y, m, pred) in enumerate(predictions):
            if i > 0:
                prev_pred = predictions[i-1][2]
                variation = pred - prev_pred
                var_str = f"{variation:+.6f}"
            else:
                var_str = "N/A"
            
            print(f"{y}-{m:02d}      | {pred:12.6f} | {var_str:>12}")
        
        print("=" * 70)
        
        if predictions:
            avg_pred = np.mean([p[2] for p in predictions])
            print(f"Moyenne prédite: {avg_pred:.6f}")
            print(f"Features utilisées: {len(self.selected_features)}")
    
    def plot_results(self, full_df: pd.DataFrame, predictions: List[Tuple[int, int, float]]) -> None:
        """Enhanced visualization with feature information"""
        logger.info("📊 Génération des graphiques")
        
        full_df = full_df.sort_values(["annee", "mois"]).reset_index(drop=True)
        dates = pd.to_datetime(full_df["annee"].astype(str) + "-" + full_df["mois"].astype(str))
        
        # Filter recent data for better visualization
        recent_mask = dates >= '2020-01-01'
        recent_dates = dates[recent_mask]
        recent_values = full_df["inflation_mom"][recent_mask]
        
        plt.figure(figsize=(16, 10))
        
        # Plot historical data and predictions
        plt.subplot(2, 2, 1)
        plt.plot(recent_dates, recent_values, label="Inflation réelle", marker='o', alpha=0.7, linewidth=2)
        
        # Plot predictions
        pred_dates = pd.to_datetime([f"{y}-{m}" for y, m, _ in predictions])
        pred_values = [p for _, _, p in predictions]
        plt.plot(pred_dates, pred_values, label="Inflation prédite", marker='X', 
                linestyle='--', color='red', linewidth=3, markersize=10)
        
        plt.title("Inflation mensuelle - Historique et Prédictions", fontsize=12, fontweight='bold')
        plt.xlabel("Date")
        plt.ylabel("Inflation mensuelle (%)")
        plt.grid(True, alpha=0.3)
        plt.legend()
        
        # Statistics subplot
        plt.subplot(2, 2, 2)
        if predictions:
            months = [f"{y}-{m:02d}" for y, m, _ in predictions]
            values = [p for _, _, p in predictions]
            plt.bar(months, values, color='skyblue', alpha=0.7)
            plt.title("Prédictions détaillées par mois", fontsize=12)
            plt.ylabel("Inflation (%)")
            plt.xticks(rotation=45)
            plt.grid(True, alpha=0.3)
        
        # Feature importance subplot
        plt.subplot(2, 2, 3)
        if self.selected_features and self.feature_importance_scores:
            top_features = self.selected_features[:8]
            if 'gbt_importance' in self.feature_importance_scores:
                scores = [self.feature_importance_scores['gbt_importance'].get(f, 0) for f in top_features]
                plt.barh(range(len(top_features)), scores, color='lightgreen', alpha=0.7)
                plt.yticks(range(len(top_features)), top_features)
                plt.title("Top Features (Importance)", fontsize=12)
                plt.xlabel("Score")
        
        # Model info subplot
        plt.subplot(2, 2, 4)
        info_text = f"Features sélectionnées: {len(self.selected_features)}\n"
        info_text += f"Features totales: {len(self.all_features)}\n"
        if predictions:
            info_text += f"Prédictions: {len(predictions)} mois\n"
            info_text += f"Moyenne: {np.mean([p[2] for p in predictions]):.4f}%"
        plt.text(0.1, 0.5, info_text, fontsize=12, verticalalignment='center')
        plt.axis('off')
        plt.title("Informations du modèle", fontsize=12)
        
        plt.tight_layout()
        try:
            st.pyplot(plt.gcf())
        except:
            plt.show()
        plt.close()
    
    def run_full_pipeline(self, parquet_path: str, start_month: int = 4, end_month: int = 9) -> List[Tuple[int, int, float]]:
        try:
            start_time = datetime.now()
            
            self.load_and_prepare_data(parquet_path)
            df_pandas = self.add_lag_features()
            df_pandas = self.create_future_periods(df_pandas, start_month=start_month, end_month=end_month)
            train_df, future_df = self.preprocess_data(df_pandas)
            self.build_and_train_model(train_df)
            predictions = self.predict_iteratively(df_pandas, start_month=start_month, end_month=end_month)
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

def run_gradient_boosting(nb_mois: int = 6) -> pd.DataFrame:
    parquet_path = r"C:\Users\user\Desktop\streamlit\data\fichierpred.parquet"
    predictor = InflationPredictor()

    start_month = 4
    end_month = start_month + nb_mois - 1
    if end_month > 12:
        raise ValueError("Le nombre de mois à prédire dépasse décembre 2025")

    predictions = predictor.run_full_pipeline(parquet_path, start_month=start_month, end_month=end_month)

    if predictions:
        df_pred = pd.DataFrame(predictions, columns=["annee", "mois", "inflation_pred"])
        df_pred["Date"] = pd.to_datetime(df_pred["annee"].astype(str) + "-" + df_pred["mois"].astype(str) + "-01").dt.date
        return df_pred[["Date", "inflation_pred"]]
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

    df_predictions = run_gradient_boosting(nb_mois=nb_mois)
    print(df_predictions)