import pandas as pd
import sys
import os

def preprocess(input_path, output_path):
    df = pd.read_csv(input_path)

    si = (
        df[df['sim_type'] == 'stakeholder_interview']
        [['student_id', 'classroom', 'scenario', 'level', 'transcript']]
        .rename(columns={'transcript': 'transcript_user'})
    )
    cc = (
        df[df['sim_type'] == 'client_conversation']
        [['student_id', 'transcript']]
        .rename(columns={'transcript': 'transcript_client'})
    )

    # left join keeps students who at least completed the stakeholder interview
    merged = si.merge(cc, on='student_id', how='left')

    merged['participant_id'] = merged['student_id']
    merged['simulation'] = (
        merged['scenario']
        .str.lower()
        .str.replace(' ', '_', regex=False)
        .str.replace('é', 'e', regex=False)
        .str.replace("'", '', regex=False)
    )
    merged['completed_user'] = merged['transcript_user'].apply(
        lambda x: 'Complete' if pd.notna(x) and str(x).strip() else 'Incomplete'
    )
    merged['completed_client'] = merged['transcript_client'].apply(
        lambda x: 'Complete' if pd.notna(x) and str(x).strip() else 'Incomplete'
    )
    merged['batch'] = merged['classroom']

    out = merged[['participant_id', 'simulation', 'completed_user', 'transcript_user',
                  'completed_client', 'transcript_client', 'batch']]

    out.to_csv(output_path, index=False)
    print(f"Saved {len(out)} students → {output_path}")
    print(out[['participant_id', 'simulation', 'completed_user', 'completed_client', 'batch']].head(5).to_string())
    print("\nBatch counts:")
    print(out['batch'].value_counts().sort_index().to_string())
    print("\nSimulation counts:")
    print(out['simulation'].value_counts().to_string())
    print()


if __name__ == '__main__':
    base = os.path.dirname(__file__)

    # 186-student dataset (April 20)
    preprocess(
        '/Users/tanvikadam/Downloads/synthetic_300_2026-04-20.csv',
        os.path.join(base, 'synthetic_186_students_2026-04-20.csv')
    )

    # 300-student dataset (April 21)
    preprocess(
        '/Users/tanvikadam/Downloads/synthetic_300_2026-04-21.csv',
        os.path.join(base, 'synthetic_300_students_2026-04-21.csv')
    )
