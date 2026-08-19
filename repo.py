#!/usr/bin/env python3
"""
build_vocab.py
Clones the TOEFL vocabulary dataset and copies the CSV to the project root.
"""

import os
import subprocess
import sys
import shutil

REPO_URL = "https://github.com/gungorkaya-eng/toefl-essential-vocabulary-dataset.git"
REPO_DIR = "toefl-essential-vocabulary-dataset"
CSV_SOURCE = os.path.join(REPO_DIR, "toefl_essential_vocabulary.csv")
CSV_TARGET = "toefl_words.csv"

def clone_or_pull_repo():
    if os.path.exists(REPO_DIR):
        print(f"📁 Repository exists. Pulling latest...")
        try:
            subprocess.run(["git", "-C", REPO_DIR, "pull"], check=True, capture_output=True)
            print("✅ Pulled latest.")
        except Exception:
            print("⚠️ Pull failed. Using existing.")
    else:
        print(f"📥 Cloning {REPO_URL} ...")
        try:
            subprocess.run(["git", "clone", REPO_URL, REPO_DIR], check=True, capture_output=True)
            print("✅ Clone successful.")
        except Exception as e:
            print(f"❌ Clone failed: {e}")
            sys.exit(1)

def copy_csv():
    if not os.path.exists(CSV_SOURCE):
        print(f"❌ CSV not found at {CSV_SOURCE}")
        sys.exit(1)
    shutil.copy2(CSV_SOURCE, CSV_TARGET)
    print(f"✅ Copied CSV to {CSV_TARGET}")

if __name__ == "__main__":
    clone_or_pull_repo()
    copy_csv()