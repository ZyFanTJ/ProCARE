
import pandas as pd
import numpy as np
from pathlib import Path

def create_dummy_excel(filename="test_data.xlsx"):
    # Set seed for reproducibility
    np.random.seed(42)
    
    # Generate dummy data
    n_rows = 100
    data = {
        "PatientID": range(1, n_rows + 1),
        "Age": np.random.randint(18, 90, n_rows),
        "Gender": np.random.choice(["Male", "Female"], n_rows),
        "Group": np.random.choice(["Control", "Treatment"], n_rows),
        "Outcome_Score": np.random.normal(50, 10, n_rows),
        "Admission_Date": pd.date_range(start="2023-01-01", periods=n_rows, freq="D"),
        "Status": np.random.choice(["Discharged", "Deceased", "Transfer"], n_rows, p=[0.8, 0.1, 0.1])
    }
    
    df = pd.DataFrame(data)
    
    # Create file path
    file_path = Path(__file__).parent / filename
    
    # Save to Excel
    df.to_excel(file_path, index=False)
    print(f"Dummy Excel file created at: {file_path}")
    return str(file_path)

if __name__ == "__main__":
    create_dummy_excel()
