"""
Extract forensic logs from Docker Compose worker logs.
Works on Windows PowerShell.
"""
import subprocess
import sys
import re

def extract_forensic_logs():
    """Extract [FORENSIC] and [PIPELINE DEBUG] logs from Docker worker."""
    try:
        # Run docker-compose logs command
        result = subprocess.run(
            ['docker-compose', 'logs', '--tail=200', 'worker'],
            capture_output=True,
            text=True,
            check=True
        )
        
        lines = result.stdout.split('\n')
        
        # Filter for forensic and pipeline debug logs
        forensic_patterns = [
            r'\[FORENSIC\]',
            r'\[PIPELINE DEBUG\]',
            r'Task.*started for job',
            r'Callback invoked',
            r'Business saved to DB',
            r'Event emitted',
            r'ZERO LISTINGS',
            r'Selector match counts',
            r'HTTP \d+ for',
            r'BOT DETECTION',
            r'Failed to fetch',
            r'NO BUSINESS DATA',
        ]
        
        print("=" * 80)
        print("FORENSIC LOG ANALYSIS")
        print("=" * 80)
        print()
        
        found_logs = []
        for line in lines:
            for pattern in forensic_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    found_logs.append(line)
                    break
        
        if found_logs:
            print(f"Found {len(found_logs)} relevant log lines:\n")
            for log in found_logs:
                print(log)
        else:
            print("No forensic logs found. Showing last 50 worker lines:\n")
            for line in lines[-50:]:
                if line.strip():
                    print(line)
        
        print()
        print("=" * 80)
        
    except subprocess.CalledProcessError as e:
        print(f"Error running docker-compose: {e}")
        print("Make sure Docker Compose is running and worker service exists.")
        sys.exit(1)
    except FileNotFoundError:
        print("docker-compose command not found.")
        print("Make sure Docker Compose is installed and in PATH.")
        sys.exit(1)

if __name__ == "__main__":
    extract_forensic_logs()

