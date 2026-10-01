"""Comprehensive incident retrieval & multi-agent evaluation benchmark."""
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data import load_incidents
from app.retrieval import IncidentRetriever
from app.evaluation import run_retrieval_evaluation, BENCHMARK_CASES

def main():
    root = Path(__file__).resolve().parents[1]
    data_path = root / "data" / "incidents.csv"
    print(f"Loading incidents from: {data_path}")
    df = load_incidents(data_path)
    print(f"Loaded {len(df):,} incidents. Initializing hybrid retriever...")
    
    retriever = IncidentRetriever(df)
    print("Running comprehensive evaluation benchmark...")
    
    metrics = run_retrieval_evaluation(retriever)
    
    print("\n" + "="*50)
    print("      INCIDENTIQ RETRIEVAL EVALUATION REPORT      ")
    print("="*50)
    print(f"Total Benchmark Cases: {metrics['total_test_cases']}")
    print(f"Precision@1 (Top-1 Accuracy):  {metrics['precision_at_1'] * 100:.2f}%")
    print(f"Hit Rate@3:                    {metrics['hit_rate_at_3'] * 100:.2f}%")
    print(f"Hit Rate@5:                    {metrics['hit_rate_at_5'] * 100:.2f}%")
    print(f"Mean Reciprocal Rank (MRR):    {metrics['mean_reciprocal_rank_mrr']:.4f}")
    print(f"Mean Average Precision (MAP):  {metrics['mean_average_precision_map']:.4f}")
    print(f"Average Query Latency:         {metrics['average_query_latency_ms']:.2f} ms")
    print(f"Overall Evaluation Grade:      {metrics['evaluation_grade']}")
    print("="*50)
    
    out_file = root / "evaluation_results.json"
    out_file.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nDetailed evaluation results saved to: {out_file}")

if __name__ == "__main__":
    main()
