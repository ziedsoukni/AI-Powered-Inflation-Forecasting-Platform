import pandas as pd
import numpy as np
from itertools import combinations
from collections import defaultdict, Counter
import json
from datetime import datetime
from typing import Dict, List, FrozenSet

class SuperOptimizedAprioriAnalyzer:
    def __init__(self, min_support=0.02, min_confidence=0.3, min_lift=0.8, max_rules=20):
        """
        Analyseur Apriori super optimisé - résout tous les problèmes
        """
        self.min_support = min_support
        self.min_confidence = min_confidence
        self.min_lift = min_lift
        self.max_rules = max_rules
        
        # Structures optimisées
        self.data = None
        self.transactions = []
        self.item_frequencies = Counter()
        self.frequent_itemsets = {}
        self.best_rules = defaultdict(list)
        self.perfect_formulas = {}
        
        # Variables à exclure
        self.exclude_vars = {'id', 'annee', 'datetime', 'mois', 'trimestre', 'date'}
        self.inflation_levels = ['1', '2', '3']
        
    def load_and_process_data(self, file_path: str) -> bool:
        """Chargement et traitement optimisé des données"""
        try:
            # Chargement rapide
            records = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        record = {}
                        for pair in line.strip().split(','):
                            if ':' in pair:
                                k, v = pair.split(':', 1)
                                record[k.strip()] = v.strip()
                        records.append(record)
            
            self.data = pd.DataFrame(records)
            print(f"✅ {len(self.data)} enregistrements chargés")
            
            # Traitement immédiat des transactions
            self._create_smart_transactions()
            return True
            
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return False
    
    def _create_smart_transactions(self):
        """Création intelligente des transactions"""
        print("🔄 Création des transactions optimisées...")
        
        # Identifier colonnes utiles
        useful_cols = [col for col in self.data.columns 
                      if col.lower() not in self.exclude_vars]
        
        print(f"📊 {len(useful_cols)} variables utilisées")
        
        # Pré-calculer les fréquences d'items
        all_items = Counter()
        raw_transactions = []
        
        for _, row in self.data.iterrows():
            items = set()
            for col in useful_cols:
                if col in row and pd.notna(row[col]):
                    value = str(row[col]).strip()
                    if value and value != 'nan':
                        item = f"{col}={value}"
                        items.add(item)
                        all_items[item] += 1
            
            if len(items) >= 2:  # Transaction valide
                raw_transactions.append(frozenset(items))
        
        # Filtrage intelligent des items rares
        min_freq = max(1, len(raw_transactions) * 0.01)  # 1% minimum
        frequent_items = {item for item, freq in all_items.items() if freq >= min_freq}
        
        # Créer transactions finales
        for raw_trans in raw_transactions:
            filtered_trans = raw_trans.intersection(frequent_items)
            if len(filtered_trans) >= 2:
                self.transactions.append(filtered_trans)
        
        self.item_frequencies = Counter()
        for trans in self.transactions:
            self.item_frequencies.update(trans)
        
        print(f"✅ {len(self.transactions)} transactions créées")
        print(f"📈 {len(frequent_items)} items fréquents détectés")
        
        # Vérifier présence inflation
        inflation_items = [item for item in frequent_items if 'inflation_mom_level=' in item]
        print(f"🎯 Niveaux d'inflation trouvés: {len(inflation_items)}")
    
    def _calculate_support(self, itemset: FrozenSet[str]) -> float:
        """Calcul de support ultra-rapide"""
        if not self.transactions:
            return 0
        return sum(1 for trans in self.transactions if itemset.issubset(trans)) / len(self.transactions)
    
    def generate_frequent_itemsets(self):
        """Génération optimisée des itemsets fréquents"""
        print("🔍 Génération des itemsets fréquents...")
        
        # 1-itemsets avec seuils adaptatifs
        frequent_1 = {}
        for item, freq in self.item_frequencies.items():
            support = freq / len(self.transactions)
            
            # Seuil adaptatif
            threshold = (0.01 if 'inflation_mom_level=' in item 
                        else max(0.02, self.min_support * 0.8))
            
            if support >= threshold:
                frequent_1[frozenset([item])] = support
        
        self.frequent_itemsets[1] = frequent_1
        print(f"   1-itemsets: {len(frequent_1)}")
        
        # Itemsets plus grands
        current_frequent = list(frequent_1.keys())
        k = 2
        
        while current_frequent and k <= 4:  # Max 4-itemsets
            candidates = self._generate_candidates(current_frequent)
            frequent_k = {}
            
            for candidate in candidates:
                support = self._calculate_support(candidate)
                
                # Seuil adaptatif
                has_inflation = any('inflation_mom_level=' in item for item in candidate)
                threshold = (0.01  if has_inflation 
                           else max(0.02, self.min_support * 0.9))
                
                if support >= threshold:
                    frequent_k[candidate] = support
            
            if frequent_k:
                self.frequent_itemsets[k] = frequent_k
                current_frequent = list(frequent_k.keys())
                print(f"   {k}-itemsets: {len(frequent_k)}")
            else:
                break
            k += 1
    
    def _generate_candidates(self, frequent_items: List[FrozenSet[str]]) -> List[FrozenSet[str]]:
        """Génération rapide de candidats"""
        candidates = []
        items_list = list(frequent_items)
        
        for i in range(len(items_list)):
            for j in range(i + 1, len(items_list)):
                union = items_list[i] | items_list[j]
                if len(union) == len(items_list[i]) + 1:
                    candidates.append(union)
        
        return candidates
    
    def generate_optimized_rules(self):
        """Génération optimisée des meilleures règles"""
        print("🎯 Génération des règles optimisées...")
        
        all_rules = []
        
        # Pour chaque niveau d'inflation
        for level in self.inflation_levels:
            target_item = f"inflation_mom_level={level}"
            level_rules = []
            
            # Chercher dans tous les itemsets fréquents
            for k, itemsets in self.frequent_itemsets.items():
                if k < 2:
                    continue
                
                for itemset, itemset_support in itemsets.items():
                    if target_item in itemset:
                        antecedent_items = itemset - frozenset([target_item])
                        
                        # Générer règles avec 1-3 antécédents
                        for r in range(1, min(len(antecedent_items) + 1, 6)):
                            for ant_combo in combinations(antecedent_items, r):
                                antecedent = frozenset(ant_combo)
                                
                                # Calculer métriques
                                ant_support = self._calculate_support(antecedent)
                                if ant_support == 0:
                                    continue
                                
                                confidence = itemset_support / ant_support
                                cons_support = self._calculate_support(frozenset([target_item]))
                                lift = confidence / cons_support if cons_support > 0 else 0
                                
                                # Métriques avancées
                                kulc = 0.5 * (confidence + (itemset_support / cons_support))
                                conviction = ((1 - cons_support) / (1 - confidence) 
                                            if confidence < 1.0 else float('inf'))
                                
                                # Score composite
                                quality_score = (confidence * 0.4 + lift * 0.3 + 
                                               kulc * 0.2 + min(conviction/10, 0.1) * 0.1)
                                
                                # Filtres permissifs
                                if (confidence >= self.min_confidence and 
                                    lift >= self.min_lift and 
                                    quality_score > 0.5):
                                    
                                    rule = {
                                        'antecedent': list(antecedent),
                                        'consequent': target_item,
                                        'support': itemset_support,
                                        'confidence': confidence,
                                        'lift': lift,
                                        'kulc': kulc,
                                        'conviction': min(conviction, 99.9),
                                        'quality_score': quality_score,
                                        'level': level
                                    }
                                    level_rules.append(rule)
            
            # Sélectionner les meilleures règles
            level_rules.sort(key=lambda x: x['quality_score'], reverse=True)
            best_level_rules = level_rules[:self.max_rules]
            
            self.best_rules[level] = best_level_rules
            all_rules.extend(best_level_rules)
            
            print(f"   Niveau {level}: {len(best_level_rules)} règles")
        
        print(f"✅ Total: {len(all_rules)} règles générées")
    
    def create_perfect_formulas(self):
        """Création des formules parfaites"""
        print("🎯 Création des formulas parfaites...")
        
        for level in self.inflation_levels:
            rules = self.best_rules.get(level, [])
            
            if not rules:
                self.perfect_formulas[level] = {
                    'level': level,
                    'formula': f"Données insuffisantes pour niveau {level}",
                    'confidence': 0,
                    'quality': 0
                }
                continue
            
            best_rule = rules[0]
            
            # Créer formule lisible
            conditions = []
            for item in best_rule['antecedent']:
                if '=' in item:
                    var, val = item.split('=', 1)
                    var_clean = var.replace('_level', '').replace('_', ' ').title()
                    conditions.append(f"{var_clean}={val}")
            
            formula_text = f"Si {' ET '.join(conditions)} → Inflation Niveau {level}"
            
            # Métriques de qualité
            avg_confidence = np.mean([r['confidence'] for r in rules[:5]])
            avg_quality = np.mean([r['quality_score'] for r in rules[:5]])
            
            self.perfect_formulas[level] = {
                'level': level,
                'formula': formula_text,
                'primary_rule': {
                    'conditions': best_rule['antecedent'],
                    'confidence': best_rule['confidence'],
                    'lift': best_rule['lift'],
                    'quality_score': best_rule['quality_score']
                },
                'statistics': {
                    'avg_confidence': avg_confidence,
                    'avg_quality': avg_quality,
                    'total_rules': len(rules)
                },
                'alternatives': [
                    {
                        'conditions': r['antecedent'],
                        'confidence': r['confidence'],
                        'lift': r['lift']
                    } for r in rules[1:11]
                ]
            }
        
        print(f"✅ {len(self.perfect_formulas)} formules créées")
    
    def display_results(self):
        """Affichage optimisé des résultats"""
        print("\n" + "="*80)
        print("🏆 FORMULES PARFAITES - VERSION SUPER OPTIMISÉE")
        print("="*80)
        
        for level in self.inflation_levels:
            if level not in self.perfect_formulas:
                continue
            
            formula = self.perfect_formulas[level]
            print(f"\n🎯 NIVEAU {level}")
            print("-" * 50)
            print(f"📋 {formula['formula']}")
            
            if 'primary_rule' in formula and formula['primary_rule']:
                rule = formula['primary_rule']
                stats = formula['statistics']
                
                print(f"📊 Confiance: {rule['confidence']:.1%} | "
                      f"Lift: {rule['lift']:.2f} | "
                      f"Qualité: {rule['quality_score']:.2f}")
                print(f"📈 Moyenne: {stats['avg_confidence']:.1%} confiance | "
                      f"{stats['total_rules']} règles total")
                
                # Alternatives
                if formula.get('alternatives'):
                    print("🔄 Alternatives:")
                    for i, alt in enumerate(formula['alternatives'][:20], 1):
                        conds = []
                        for cond in alt['conditions']:
                            if '=' in cond:
                                var, val = cond.split('=', 1)
                                var_clean = var.replace('_level', '').replace('_', ' ').title()
                                conds.append(f"{var_clean}={val}")
                        print(f"   {i}. {' ET '.join(conds)} "
                              f"(Conf: {alt['confidence']:.1%})")
        
        # Stats globales
        all_rules = [r for rules in self.best_rules.values() for r in rules]
        if all_rules:
            avg_conf = np.mean([r['confidence'] for r in all_rules])
            avg_lift = np.mean([r['lift'] for r in all_rules])
            
            print(f"\n📊 STATISTIQUES GLOBALES")
            print("-" * 30)
            print(f"Total règles: {len(all_rules)}")
            print(f"Confiance moyenne: {avg_conf:.1%}")
            print(f"Lift moyen: {avg_lift:.2f}")
            print(f"Itemsets fréquents: {sum(len(v) for v in self.frequent_itemsets.values())}")
    
    def export_results(self, filename: str = "super_optimized_results.json"):
        """Export rapide des résultats"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'algorithm': 'Super Optimized Apriori',
            'parameters': {
                'min_support': self.min_support,
                'min_confidence': self.min_confidence,
                'min_lift': self.min_lift,
                'max_rules': self.max_rules
            },
            'statistics': {
                'total_records': len(self.data),
                'total_transactions': len(self.transactions),
                'frequent_itemsets': sum(len(v) for v in self.frequent_itemsets.values()),
                'total_rules': sum(len(rules) for rules in self.best_rules.values())
            },
            'perfect_formulas': self.perfect_formulas,
            'best_rules': dict(self.best_rules)
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Résultats exportés: {filename}")
    
    def run_complete_analysis(self, file_path: str) -> bool:
        """Analyse complète super optimisée"""
        print("🚀 ANALYSE SUPER OPTIMISÉE - DÉMARRAGE")
        print("="*50)
        
        # Pipeline optimisé
        if not self.load_and_process_data(file_path):
            return False
        
        if not self.transactions:
            print("❌ Aucune transaction valide créée!")
            return False
        
        self.generate_frequent_itemsets()
        self.generate_optimized_rules()
        self.create_perfect_formulas()
        self.display_results()
        self.export_results()
        
        print(f"\n🎉 ANALYSE TERMINÉE AVEC SUCCÈS!")
        print(f"📋 Résumé: {len(self.data)} obs. → {len(self.transactions)} trans. → "
              f"{sum(len(v) for v in self.frequent_itemsets.values())} itemsets → "
              f"{sum(len(rules) for rules in self.best_rules.values())} règles")
        
        return True

def main():
    """Fonction principale super optimisée"""
    print("⚡ LANCEMENT SUPER OPTIMISÉ")
    
    # Configuration équilibrée
    analyzer = SuperOptimizedAprioriAnalyzer(
        min_support=0.03,    # 1.5% - Plus permissif
        min_confidence=0.6,  # 25% - Équilibré
        min_lift=1.2,        # 0.8 - Permissif
        max_rules=10         # Top 15 par niveau
    )
    
    file_path = r"C:\Users\user\Desktop\streamlit\data\\skeyepredict_inflation.dat"
    
    import os
    if not os.path.exists(file_path):
        print(f"❌ Fichier non trouvé: {file_path}")
        return
    
    success = analyzer.run_complete_analysis(file_path)
    
    if success:
        print("\n✨ ANALYSE SUPER OPTIMISÉE RÉUSSIE!")
        print("📄 Consultez 'super_optimized_results.json' pour tous les détails")
    else:
        print("\n❌ Erreur lors de l'analyse")

if __name__ == "__main__":
    main()