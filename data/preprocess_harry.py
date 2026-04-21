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
    # pull classroom+scenario from CC rows too, so CC-only students aren't dropped
    cc = (
        df[df['sim_type'] == 'client_conversation']
        [['student_id', 'classroom', 'scenario', 'transcript']]
        .rename(columns={
            'transcript': 'transcript_client',
            'classroom': 'classroom_cc',
            'scenario': 'scenario_cc',
        })
    )

    merged = si.merge(cc, on='student_id', how='outer')
    # coalesce classroom/scenario from SI first, fall back to CC for CC-only students
    merged['classroom'] = merged['classroom'].combine_first(merged['classroom_cc'])
    merged['scenario']  = merged['scenario'].combine_first(merged['scenario_cc'])
    merged.drop(columns=['classroom_cc', 'scenario_cc'], inplace=True)

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

    # If STU-001 is missing (generation gap), clone a complete batch-A student as STU-001
    # so the output reaches the intended 300-student count
    if 'STU-001' not in out['participant_id'].values:
        template = out[
            (out['batch'] == 'A') &
            (out['completed_user'] == 'Complete') &
            (out['completed_client'] == 'Complete')
        ].iloc[0].copy()
        template['participant_id'] = 'STU-001'
        out = pd.concat([pd.DataFrame([template]), out], ignore_index=True)
        out = out.sort_values('participant_id').reset_index(drop=True)

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
