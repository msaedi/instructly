# Seed Data System

This directory contains YAML-based seed data for the InstaInstru platform.

## Structure

```
seed_data/
├── catalog/                    # Service catalog (categories and services)
│   ├── categories.yaml        # Service categories
│   └── services.yaml          # Predefined services
├── instructors.yaml           # Instructor profiles and their services
├── students.yaml              # Student accounts
├── availability_patterns.yaml # Reusable availability patterns
├── bookings.yaml             # Sample bookings
├── config.yaml               # Seed configuration
└── service_catalog_mapping.yaml # Maps instructor service names to catalog
```

## Architecture

### Unified Catalog System

The service catalog is managed by a single script: `seed_catalog_only.py`

1. **Standalone Usage** (e.g., production catalog updates):
   ```bash
   python scripts/seed_catalog_only.py
   ```

2. **Integrated Usage** (development seeding):
   ```bash
   USE_TEST_DATABASE=true python scripts/reset_and_seed_yaml.py
   ```
   This automatically calls `seed_catalog_only.py` first.

### Key Principles

- **Single Source of Truth**: All catalog seeding logic is in `seed_catalog_only.py`
- **YAML-Based**: All data is defined in YAML files for easy maintenance
- **Reusable**: The catalog seeding function can be imported by other scripts
- **Idempotent**: Running the catalog seed multiple times updates existing data

### Service Catalog

The catalog provides:
- 8 service categories (Music & Arts, Academic, Languages, etc.)
- 50+ predefined services with standardized names
- Search terms for enhanced discovery
- NYC market-based pricing guidelines
- Typical session durations

### Instructor Services

When seeding instructors:
1. The catalog is seeded first (if not already present)
2. Instructors' services are mapped to catalog entries using `service_catalog_mapping.yaml`
3. Instructors can customize pricing and descriptions while using catalog services

## Usage

### Development
```bash
# Reset and seed everything with test data
USE_TEST_DATABASE=true python scripts/reset_and_seed_yaml.py
```

### Production
```bash
# Seed only the service catalog
python scripts/seed_catalog_only.py

# Or with specific database
python scripts/seed_catalog_only.py --db-url postgresql://...
```

### Adding New Services

1. Edit `catalog/services.yaml` to add the service
2. Run `seed_catalog_only.py` to update the database
3. Update `service_catalog_mapping.yaml` if needed for instructor mapping
