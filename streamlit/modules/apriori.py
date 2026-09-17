import pandas as pd
import numpy as np
from itertools import combinations
from collections import defaultdict
import json
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set, FrozenSet

class AprioriInflationAnalyzer:
    def __init__(self, min_support=0.05, min_confidence=0.6, min_lift=1.1, max_antecedents=5):
        """
        Analyseur d'associations utilisant l'algorithme Apriori optimisé
        
        Parameters:
        - min_support: Support minimum (0.05 = 5%)
        - min_confidence: Confiance minimum (0.6 = 60%)
        - min_lift: Lift minimum (1.1)
        - max_antecedents: Nombre maximum d'antécédents par règle
        """
        self.min_support = min_support
        self.min_confidence = min_confidence
        self.min_lift = min_lift
        self.max_antecedents = max_antecedents
        self.data = None
        self.transactions = []
        self.frequent_itemsets = {}  # {k: [itemsets]} où k est la taille
        self.association_rules = []
        self.perfect_formulas = {}
        self.inflation_levels = ['1', '2', '3', '4', '5']
        self.item_support_cache = {}  # Cache pour les supports
        
    def load_data(self, file_path: str) -> bool:
        """Charge les données depuis le fichier .dat"""
        try:
            data = []
            with open(file_path, 'r', encoding='utf-8') as file:
                for line_num, line in enumerate(file, 1):
                    line = line.strip()
                    if line:
                        record = {}
                        pairs = line.split(',')
                        for pair in pairs:
                            if ':' in pair:
                                key, value = pair.split(':', 1)
                                record[key.strip()] = value.strip()
                        data.append(record)
            
            self.data = pd.DataFrame(data)
            print(f"✅ Données chargées: {len(self.data)} enregistrements")
            print(f"📊 Colonnes: {list(self.data.columns)}")
            
            if 'inflation_mom_level' in self.data.columns:
                distribution = self.data['inflation_mom_level'].value_counts().sort_index()
                print(f"📈 Distribution des niveaux d'inflation:")
                for level, count in distribution.items():
                    print(f"   Niveau {level}: {count} observations ({count/len(self.data)*100:.1f}%)")
            
            return True
            
        except Exception as e:
            print(f"❌ Erreur lors du chargement: {e}")
            return False
    
    def prepare_transactions(self):
        """Transforme les données en transactions pour Apriori"""
        self.transactions = []
        
        exclude_cols = ['id', 'annee', 'Datetime', 'mois', 'trimestre']
        priority_cols = [
            'pib_croissance_level', 'chomage_level', 'taux_interet_level',
            'prix_petrole_level', 'indice_dollar_level', 'masse_monetaire_level',
            'deficit_budgetaire_level', 'balance_commerciale_level'
        ]
        
        print(f"🔄 Préparation des transactions...")
        
        for idx, row in self.data.iterrows():
            transaction = set()  # Utiliser un set pour éviter les doublons
            
            # Ajouter les colonnes prioritaires
            for col in priority_cols:
                if col in row and pd.notna(row[col]) and str(row[col]).strip():
                    transaction.add(f"{col}={row[col]}")
            
            # Ajouter les autres colonnes
            for col, value in row.items():
                if (col not in exclude_cols and 
                    col not in priority_cols and 
                    col != 'inflation_mom_level' and
                    pd.notna(value) and 
                    str(value).strip()):
                    transaction.add(f"{col}={value}")
            
            # Ajouter l'inflation (obligatoire)
            if 'inflation_mom_level' in row and pd.notna(row['inflation_mom_level']):
                transaction.add(f"inflation_mom_level={row['inflation_mom_level']}")
            
            if len(transaction) >= 2:  # Au moins 2 items pour être utile
                self.transactions.append(frozenset(transaction))
        
        print(f"✅ {len(self.transactions)} transactions créées")
        self.verify_inflation_coverage()
    
    def verify_inflation_coverage(self):
        """Vérifie la couverture des niveaux d'inflation"""
        level_counts = defaultdict(int)
        for transaction in self.transactions:
            for item in transaction:
                if item.startswith('inflation_mom_level='):
                    level = item.split('=')[1]
                    level_counts[level] += 1
        
        print(f"📊 Couverture des niveaux d'inflation:")
        for level in self.inflation_levels:
            count = level_counts.get(level, 0)
            percentage = (count / len(self.transactions)) * 100 if self.transactions else 0
            print(f"   Niveau {level}: {count} transactions ({percentage:.1f}%)")
    
    def calculate_support(self, itemset: FrozenSet[str]) -> float:
        """Calcule le support d'un itemset avec cache"""
        if itemset in self.item_support_cache:
            return self.item_support_cache[itemset]
        
        if not self.transactions:
            return 0
        
        count = sum(1 for transaction in self.transactions if itemset.issubset(transaction))
        support = count / len(self.transactions)
        self.item_support_cache[itemset] = support
        return support
    
    def get_frequent_1_itemsets(self) -> Dict[FrozenSet[str], float]:
        """Génère les 1-itemsets fréquents"""
        print("🔍 Génération des 1-itemsets fréquents...")
        
        item_counts = defaultdict(int)
        for transaction in self.transactions:
            for item in transaction:
                item_counts[item] += 1
        
        frequent_1_itemsets = {}
        total_transactions = len(self.transactions)
        
        for item, count in item_counts.items():
            support = count / total_transactions
            itemset = frozenset([item])
            
            # Support adaptatif pour l'inflation
            if item.startswith('inflation_mom_level='):
                min_support_threshold = max(0.01, self.min_support * 0.3)
            else:
                min_support_threshold = self.min_support
            
            if support >= min_support_threshold:
                frequent_1_itemsets[itemset] = support
        
        print(f"   Trouvés: {len(frequent_1_itemsets)} 1-itemsets fréquents")
        return frequent_1_itemsets
    
    def apriori_gen(self, frequent_k_itemsets: List[FrozenSet[str]], k: int) -> List[FrozenSet[str]]:
        """Génère les candidats (k+1)-itemsets à partir des k-itemsets fréquents"""
        candidates = []
        frequent_k_list = list(frequent_k_itemsets)
        
        for i in range(len(frequent_k_list)):
            for j in range(i + 1, len(frequent_k_list)):
                itemset1 = frequent_k_list[i]
                itemset2 = frequent_k_list[j]
                
                # Union des deux itemsets
                union_itemset = itemset1 | itemset2
                
                # Vérifier que la taille est exactement k+1
                if len(union_itemset) == k + 1:
                    # Pruning: vérifier que tous les (k)-sous-ensembles sont fréquents
                    if self.has_infrequent_subset(union_itemset, frequent_k_itemsets, k):
                        continue
                    
                    candidates.append(union_itemset)
        
        return candidates
    
    def has_infrequent_subset(self, itemset: FrozenSet[str], frequent_k_itemsets: List[FrozenSet[str]], k: int) -> bool:
        """Vérifie si un itemset a un sous-ensemble non-fréquent"""
        for item in itemset:
            subset = itemset - frozenset([item])
            if len(subset) == k and subset not in frequent_k_itemsets:
                return True
        return False
    
    def run_apriori(self):
        """Exécute l'algorithme Apriori complet"""
        print("🚀 Démarrage de l'algorithme Apriori...")
        
        # Initialiser avec les 1-itemsets
        frequent_1 = self.get_frequent_1_itemsets()
        self.frequent_itemsets[1] = frequent_1
        current_frequent = list(frequent_1.keys())
        
        k = 2
        while current_frequent and k <= self.max_antecedents + 1:
            print(f"🔍 Génération des {k}-itemsets fréquents...")
            
            # Générer les candidats
            candidates = self.apriori_gen(current_frequent, k - 1)
            
            # Filtrer par support
            frequent_k = {}
            for candidate in candidates:
                support = self.calculate_support(candidate)
                
                # Support adaptatif pour les itemsets contenant l'inflation
                has_inflation = any(item.startswith('inflation_mom_level=') for item in candidate)
                min_support_threshold = max(0.01, self.min_support * 0.5) if has_inflation else self.min_support
                
                if support >= min_support_threshold:
                    frequent_k[candidate] = support
            
            print(f"   Trouvés: {len(frequent_k)} {k}-itemsets fréquents")
            
            if frequent_k:
                self.frequent_itemsets[k] = frequent_k
                current_frequent = list(frequent_k.keys())
            else:
                current_frequent = []
            
            k += 1
        
        total_itemsets = sum(len(itemsets) for itemsets in self.frequent_itemsets.values())
        print(f"✅ Apriori terminé: {total_itemsets} itemsets fréquents au total")
    
    def generate_association_rules(self):
        """Génère les règles d'association à partir des itemsets fréquents"""
        print("🔍 Génération des règles d'association...")
        self.association_rules = []
        
        for target_level in self.inflation_levels:
            print(f"   Traitement du niveau {target_level}...")
            target_inflation = f"inflation_mom_level={target_level}"
            level_rules = []
            
            # Parcourir tous les itemsets fréquents
            for k, frequent_k in self.frequent_itemsets.items():
                if k < 2:  # Besoin d'au moins 2 items pour une règle
                    continue
                
                for itemset, support in frequent_k.items():
                    if target_inflation in itemset:
                        other_items = itemset - frozenset([target_inflation])
                        
                        # Générer toutes les combinaisons d'antécédents
                        for r in range(1, min(len(other_items) + 1, self.max_antecedents + 1)):
                            for antecedent_items in combinations(other_items, r):
                                antecedent = frozenset(antecedent_items)
                                consequent = frozenset([target_inflation])
                                
                                # Calculer les métriques
                                antecedent_support = self.calculate_support(antecedent)
                                if antecedent_support == 0:
                                    continue
                                
                                confidence = support / antecedent_support
                                consequent_support = self.calculate_support(consequent)
                                lift = confidence / consequent_support if consequent_support > 0 else 0
                                
                                # Conviction
                                if confidence == 1.0:
                                    conviction = float('inf')
                                elif consequent_support == 1.0:
                                    conviction = 1.0
                                else:
                                    conviction = (1 - consequent_support) / (1 - confidence) if confidence < 1.0 else 1.0
                                
                                # Seuils adaptatifs
                                min_conf = max(0.3, self.min_confidence * 0.7)
                                min_lift_val = max(1.0, self.min_lift * 0.8)
                                
                                if confidence >= min_conf and lift >= min_lift_val:
                                    rule = {
                                        'antecedent': list(antecedent),
                                        'consequent': list(consequent),
                                        'support': support,
                                        'confidence': confidence,
                                        'lift': lift,
                                        'conviction': conviction,
                                        'inflation_level': target_level,
                                        'rule_strength': confidence * lift * min(conviction, 10)
                                    }
                                    level_rules.append(rule)
            
            # Si pas assez de règles, créer des règles basiques
            if len(level_rules) < 3:
                level_rules.extend(self.create_basic_rules_for_level(target_level))
            
            self.association_rules.extend(level_rules)
        
        # Trier par force de règle
        self.association_rules.sort(key=lambda x: x['rule_strength'], reverse=True)
        print(f"✅ Total règles générées: {len(self.association_rules)}")
        self.verify_rules_coverage()
    
    def create_basic_rules_for_level(self, level: str) -> List[Dict]:
        """Crée des règles de base pour un niveau d'inflation spécifique"""
        target_inflation = f"inflation_mom_level={level}"
        basic_rules = []
        
        # Identifier les items qui coexistent avec ce niveau
        coexisting_items = defaultdict(int)
        
        for transaction in self.transactions:
            if target_inflation in transaction:
                for item in transaction:
                    if item != target_inflation and not item.startswith('inflation_mom_level='):
                        coexisting_items[item] += 1
        
        # Créer des règles simples
        sorted_items = sorted(coexisting_items.items(), key=lambda x: x[1], reverse=True)
        
        for item, count in sorted_items[:10]:
            antecedent = frozenset([item])
            consequent = frozenset([target_inflation])
            
            antecedent_support = self.calculate_support(antecedent)
            if antecedent_support == 0:
                continue
            
            rule_support = self.calculate_support(antecedent | consequent)
            confidence = rule_support / antecedent_support
            
            consequent_support = self.calculate_support(consequent)
            lift = confidence / consequent_support if consequent_support > 0 else 0
            
            if confidence > 0.1 and lift > 0.5:
                conviction = (1 - consequent_support) / (1 - confidence) if confidence < 1.0 else 1.0
                
                basic_rules.append({
                    'antecedent': list(antecedent),
                    'consequent': list(consequent),
                    'support': rule_support,
                    'confidence': confidence,
                    'lift': lift,
                    'conviction': conviction,
                    'inflation_level': level,
                    'rule_strength': confidence * lift * min(conviction, 10)
                })
        
        return basic_rules[:5]
    
    def verify_rules_coverage(self):
        """Vérifie la couverture des règles par niveau"""
        rules_by_level = defaultdict(int)
        for rule in self.association_rules:
            rules_by_level[rule['inflation_level']] += 1
        
        print(f"📊 Couverture des règles par niveau:")
        for level in self.inflation_levels:
            count = rules_by_level.get(level, 0)
            print(f"   Niveau {level}: {count} règles")
    
    def generate_perfect_formulas(self):
        """Génère les formules parfaites pour tous les niveaux"""
        print("🎯 Génération des formules parfaites...")
        
        rules_by_level = self.get_rules_by_inflation_level()
        self.perfect_formulas = {}
        
        for level in self.inflation_levels:
            print(f"   Génération pour le niveau {level}...")
            
            level_rules = rules_by_level.get(level, [])
            
            if not level_rules:
                print(f"   ⚠️  Pas de règles pour le niveau {level}, création d'une formule de base")
                level_rules = self.create_basic_rules_for_level(level)
            
            level_rules.sort(key=lambda x: x['rule_strength'], reverse=True)
            
            # Analyser les patterns
            pattern_analysis = self.analyze_patterns(level_rules)
            
            # Créer la formule parfaite
            perfect_formula = self.create_perfect_formula(level, level_rules, pattern_analysis)
            
            self.perfect_formulas[level] = perfect_formula
        
        print(f"✅ Formules parfaites générées pour {len(self.perfect_formulas)} niveaux")
    
    def analyze_patterns(self, rules: List[Dict]) -> Dict:
        """Analyse les patterns dans les règles"""
        if not rules:
            return {
                'most_common_factors': defaultdict(int),
                'factor_combinations': defaultdict(int),
                'strength_distribution': []
            }
        
        patterns = {
            'most_common_factors': defaultdict(int),
            'factor_combinations': defaultdict(int),
            'strength_distribution': []
        }
        
        for rule in rules:
            patterns['strength_distribution'].append(rule['rule_strength'])
            
            for antecedent in rule['antecedent']:
                factor = antecedent.split('=')[0]
                patterns['most_common_factors'][factor] += 1
                
            factors = [ant.split('=')[0] for ant in rule['antecedent']]
            combo_key = ' + '.join(sorted(factors))
            patterns['factor_combinations'][combo_key] += 1
        
        return patterns
    
    def create_perfect_formula(self, level: str, rules: List[Dict], patterns: Dict) -> Dict:
        """Crée une formule parfaite pour un niveau d'inflation"""
        if not rules:
            return {
                'level': level,
                'formula': f"Données insuffisantes pour le niveau {level}",
                'primary_rule': None,
                'reliability_metrics': {
                    'avg_confidence': 0,
                    'avg_lift': 0,
                    'sample_size': 0,
                    'reliability_score': 0
                },
                'key_factors': {},
                'alternative_rules': []
            }
        
        best_rule = rules[0]
        
        # Créer la formule textuelle
        formula_conditions = []
        for antecedent in best_rule['antecedent']:
            if '=' in antecedent:
                factor, value = antecedent.split('=', 1)
                factor_name = factor.replace('_level', '').replace('_', ' ').title()
                formula_conditions.append(f"{factor_name} = {value}")
        
        formula_text = f"Si {' ET '.join(formula_conditions)} → Inflation niveau {level}"
        
        # Calculer la fiabilité
        top_rules = rules[:min(5, len(rules))]
        avg_confidence = np.mean([rule['confidence'] for rule in top_rules])
        avg_lift = np.mean([rule['lift'] for rule in top_rules])
        
        # Facteurs les plus importants
        top_factors = dict(list(patterns['most_common_factors'].items())[:5])
        
        perfect_formula = {
            'level': level,
            'formula': formula_text,
            'primary_rule': {
                'conditions': best_rule['antecedent'],
                'confidence': best_rule['confidence'],
                'lift': best_rule['lift'],
                'conviction': best_rule['conviction'],
                'strength': best_rule['rule_strength']
            },
            'reliability_metrics': {
                'avg_confidence': avg_confidence,
                'avg_lift': avg_lift,
                'sample_size': len(rules),
                'reliability_score': (avg_confidence * avg_lift * 100) / 2
            },
            'key_factors': top_factors,
            'alternative_rules': [
                {
                    'conditions': rule['antecedent'],
                    'confidence': rule['confidence'],
                    'lift': rule['lift']
                } for rule in rules[1:min(4, len(rules))]
            ]
        }
        
        return perfect_formula
    
    def get_rules_by_inflation_level(self) -> Dict:
        """Groupe les règles par niveau d'inflation"""
        rules_by_level = defaultdict(list)
        
        for rule in self.association_rules:
            level = rule['inflation_level']
            rules_by_level[level].append(rule)
        
        return dict(rules_by_level)
    
    def print_perfect_formulas(self):
        """Affiche les formules parfaites"""
        print("\n" + "="*100)
        print("🎯 FORMULES PARFAITES GÉNÉRÉES AVEC APRIORI")
        print("="*100)
        
        for level in self.inflation_levels:
            if level not in self.perfect_formulas:
                print(f"\n❌ Niveau {level}: Aucune formule générée")
                continue
                
            formula = self.perfect_formulas[level]
            
            print(f"\n{'='*80}")
            print(f"💡 NIVEAU D'INFLATION: {level}")
            print(f"{'='*80}")
            
            print(f"\n🎯 FORMULE PARFAITE:")
            print(f"   {formula['formula']}")
            
            if formula['primary_rule']:
                print(f"\n📊 MÉTRIQUES DE FIABILITÉ:")
                print(f"   • Confiance moyenne: {formula['reliability_metrics']['avg_confidence']:.1%}")
                print(f"   • Lift moyen: {formula['reliability_metrics']['avg_lift']:.2f}")
                print(f"   • Score de fiabilité: {formula['reliability_metrics']['reliability_score']:.1f}/100")
                print(f"   • Basé sur {formula['reliability_metrics']['sample_size']} règles")
                
                print(f"\n⭐ RÈGLE PRINCIPALE:")
                primary = formula['primary_rule']
                print(f"   • Confiance: {primary['confidence']:.1%}")
                print(f"   • Lift: {primary['lift']:.2f}")
                print(f"   • Force: {primary['strength']:.2f}")
                
                if formula['key_factors']:
                    print(f"\n🔑 FACTEURS CLÉS:")
                    for factor, importance in formula['key_factors'].items():
                        factor_name = factor.replace('_level', '').replace('_', ' ').title()
                        print(f"   • {factor_name}: {importance} occurrence(s)")
    
    def export_results(self, output_file: str = "apriori_inflation_results.json"):
        """Exporte les résultats"""
        rules_by_level = self.get_rules_by_inflation_level()
        level_stats = {}
        
        for level in self.inflation_levels:
            level_rules = rules_by_level.get(level, [])
            level_stats[level] = {
                'rule_count': len(level_rules),
                'avg_confidence': np.mean([r['confidence'] for r in level_rules]) if level_rules else 0,
                'avg_lift': np.mean([r['lift'] for r in level_rules]) if level_rules else 0,
                'max_strength': max([r['rule_strength'] for r in level_rules]) if level_rules else 0
            }
        
        # Statistiques Apriori
        apriori_stats = {
            'frequent_itemsets_by_size': {k: len(v) for k, v in self.frequent_itemsets.items()},
            'total_frequent_itemsets': sum(len(v) for v in self.frequent_itemsets.values()),
            'cache_hits': len(self.item_support_cache)
        }
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'algorithm': 'Apriori',
            'configuration': {
                'min_support': self.min_support,
                'min_confidence': self.min_confidence,
                'min_lift': self.min_lift,
                'max_antecedents': self.max_antecedents
            },
            'apriori_statistics': apriori_stats,
            'analysis_statistics': {
                'total_observations': len(self.data),
                'total_transactions': len(self.transactions),
                'total_rules': len(self.association_rules),
                'levels_analyzed': len(self.perfect_formulas),
                'level_statistics': level_stats
            },
            'perfect_formulas': self.perfect_formulas,
            'all_rules_by_level': rules_by_level
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Résultats exportés vers: {output_file}")
    
    def run_complete_analysis(self, file_path: str) -> bool:
        """Exécute l'analyse complète avec Apriori"""
        print("🚀 Démarrage de l'analyse avec l'algorithme Apriori...")
        
        # Chargement des données
        if not self.load_data(file_path):
            return False
        
        # Préparation des transactions
        self.prepare_transactions()
        
        # Algorithme Apriori
        self.run_apriori()
        
        # Génération des règles d'association
        self.generate_association_rules()
        
        # Génération des formules parfaites
        self.generate_perfect_formulas()
        
        # Affichage des résultats
        self.print_perfect_formulas()
        
        # Export des résultats
        self.export_results()
        
        # Résumé final
        print(f"\n🎉 ANALYSE APRIORI TERMINÉE!")
        print(f"📊 Résultats:")
        print(f"   • {len(self.data)} observations traitées")
        print(f"   • {len(self.transactions)} transactions créées")
        print(f"   • {sum(len(v) for v in self.frequent_itemsets.values())} itemsets fréquents")
        print(f"   • {len(self.association_rules)} règles d'association")
        print(f"   • {len(self.perfect_formulas)} formules parfaites")
        
        return True

def main():
    """Fonction principale utilisant Apriori"""
    # Configuration optimisée
    analyzer = AprioriInflationAnalyzer(
        min_support=0.05,     # 3% - permissif
        min_confidence=0.5,   # 50% - permissif
        min_lift=1.0,         # 1.0 - permissif
        max_antecedents=3     # Jusqu'à 5 conditions
    )
    
    # Chemin vers votre fichier
    file_path = r"C:\Users\user\Desktop\streamlit\data\skeyepredict_inflation.dat"
    
    # Vérifier l'existence du fichier
    import os
    if not os.path.exists(file_path):
        print(f"❌ Fichier non trouvé: {file_path}")
        return
    
    print(f"📁 Traitement du fichier: {file_path}")
    
    # Exécution de l'analyse
    success = analyzer.run_complete_analysis(file_path)
    
    if success:
        print("\n🎉 ANALYSE APRIORI TERMINÉE AVEC SUCCÈS!")
        print("📋 Résultats disponibles dans 'apriori_inflation_results.json'")
    else:
        print("\n❌ Erreur lors de l'analyse")

if __name__ == "__main__":
    main()