#!/usr/bin/env python3
"""
Codebase audit script for InstaInstru
Analyzes both backend and frontend structure to identify:
1. Files referencing old table names
2. Potentially obsolete files
3. Overall code organization
"""

import os
import re
from pathlib import Path
from collections import defaultdict
import json

class CodebaseAuditor:
    def __init__(self, root_path="."):
        self.root_path = Path(root_path)
        self.backend_path = self.root_path / "backend"
        self.frontend_path = self.root_path / "frontend"
        
        # Patterns to search for
        self.old_patterns = {
            'recurring_availability': r'recurring_availability|RecurringAvailability',
            'specific_date_availability': r'specific_date_availability|SpecificDateAvailability',
            'date_time_slots': r'date_time_slots|DateTimeSlot',
            'date_override_id': r'date_override_id',
            'bookings': r'booking|Booking',  # Old booking system
            'time_slots': r'time_slots|TimeSlot',  # Old time slots
            'buffer_time': r'buffer_time',
            'minimum_advance_hours': r'minimum_advance_hours',
            'default_session_duration': r'default_session_duration'
        }
        
        self.results = defaultdict(lambda: defaultdict(list))
        
    def audit(self):
        print("=" * 80)
        print("CODEBASE AUDIT REPORT")
        print("=" * 80)
        print()
        
        # Backend audit
        print("🔧 BACKEND STRUCTURE")
        print("-" * 60)
        self.audit_backend()
        
        print("\n📱 FRONTEND STRUCTURE")
        print("-" * 60)
        self.audit_frontend()
        
        print("\n🔍 PATTERN SEARCH RESULTS")
        print("-" * 60)
        self.search_patterns()
        
        print("\n📊 SUMMARY")
        print("-" * 60)
        self.print_summary()
        
    def audit_backend(self):
        if not self.backend_path.exists():
            print("Backend directory not found!")
            return
            
        # Key directories to analyze
        dirs_to_check = ['app/models', 'app/routes', 'app/schemas', 
                        'app/services', 'alembic/versions', 'scripts']
        
        for dir_path in dirs_to_check:
            full_path = self.backend_path / dir_path
            if full_path.exists():
                files = list(full_path.glob('**/*.py'))
                if files:
                    print(f"\n{dir_path}:")
                    for file in sorted(files):
                        rel_path = file.relative_to(self.backend_path)
                        size = file.stat().st_size
                        print(f"  - {rel_path} ({size:,} bytes)")
                        
                        # Check for specific patterns
                        content = file.read_text()
                        if 'booking' in content.lower() and 'availability' not in str(file):
                            self.results['potential_old_files']['booking'].append(str(rel_path))
                            
    def audit_frontend(self):
        if not self.frontend_path.exists():
            print("Frontend directory not found!")
            return
            
        # Key directories and files
        dirs_to_check = ['app', 'components', 'lib', 'types', 'utils']
        
        for dir_name in dirs_to_check:
            dir_path = self.frontend_path / dir_name
            if dir_path.exists():
                files = list(dir_path.glob('**/*.{ts,tsx,js,jsx}'))
                if files:
                    print(f"\n{dir_name}:")
                    for file in sorted(files):
                        rel_path = file.relative_to(self.frontend_path)
                        print(f"  - {rel_path}")
                        
    def search_patterns(self):
        # Search for old patterns in both backend and frontend
        for pattern_name, pattern in self.old_patterns.items():
            print(f"\n{pattern_name}:")
            
            # Backend search
            backend_matches = self.search_in_directory(self.backend_path, pattern, ['.py'])
            if backend_matches:
                print("  Backend:")
                for file, count in backend_matches.items():
                    print(f"    - {file}: {count} occurrences")
                    self.results['pattern_matches'][pattern_name].append(file)
                    
            # Frontend search
            frontend_matches = self.search_in_directory(self.frontend_path, pattern, 
                                                       ['.ts', '.tsx', '.js', '.jsx'])
            if frontend_matches:
                print("  Frontend:")
                for file, count in frontend_matches.items():
                    print(f"    - {file}: {count} occurrences")
                    self.results['pattern_matches'][pattern_name].append(file)
                    
            if not backend_matches and not frontend_matches:
                print("  No occurrences found")
                
    def search_in_directory(self, directory, pattern, extensions):
        matches = {}
        if not directory.exists():
            return matches
            
        for ext in extensions:
            for file in directory.glob(f'**/*{ext}'):
                try:
                    content = file.read_text()
                    found = re.findall(pattern, content, re.IGNORECASE)
                    if found:
                        rel_path = file.relative_to(self.root_path)
                        matches[str(rel_path)] = len(found)
                except Exception as e:
                    pass
                    
        return matches
        
    def print_summary(self):
        print("\n⚠️  Files to Update for Table Renaming:")
        
        critical_patterns = ['specific_date_availability', 'date_time_slots', 
                           'recurring_availability', 'date_override_id']
        
        all_files = set()
        for pattern in critical_patterns:
            if pattern in self.results['pattern_matches']:
                all_files.update(self.results['pattern_matches'][pattern])
                
        for file in sorted(all_files):
            print(f"  - {file}")
            
        print(f"\nTotal files to update: {len(all_files)}")
        
        # Old booking system files
        if self.results['potential_old_files']['booking']:
            print("\n⚠️  Potential old booking system files:")
            for file in self.results['potential_old_files']['booking']:
                print(f"  - {file}")
                
        # Statistics
        print("\n📈 Statistics:")
        total_patterns = sum(len(files) for files in self.results['pattern_matches'].values())
        print(f"  - Total pattern matches: {total_patterns}")
        print(f"  - Unique files with matches: {len(all_files)}")
        
        # Create a JSON output for reference
        output = {
            'files_to_update': list(all_files),
            'pattern_matches': dict(self.results['pattern_matches']),
            'potential_old_files': dict(self.results['potential_old_files'])
        }
        
        with open('codebase_audit.json', 'w') as f:
            json.dump(output, f, indent=2)
        print("\n💾 Detailed results saved to codebase_audit.json")

if __name__ == "__main__":
    auditor = CodebaseAuditor()
    auditor.audit()
