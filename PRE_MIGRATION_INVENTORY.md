# Pre-Migration Inventory: Documentation Consolidation

## Overview
This document outlines the migration plan to consolidate all documentation from `/backend/docs/` and `/docs/` into a single `/docs/` directory at the project root.

## Migration Summary
- **Total files to move**: 53 files from `/backend/docs/`
- **Files to keep in place**: 10 files already in `/docs/`
- **Files requiring path updates**: 13 files
- **README files to merge**: 2 files

## Directory Structure After Migration

```
/docs/
├── api/                    # API documentation and specs
├── architecture/           # Architecture decisions and patterns
├── a-team-deliverables/    # Design team deliverables
├── development/            # Development guides and testing
├── flows/                  # (EXISTING) User flow documentation
├── infrastructure/         # Infrastructure and SSL setup
├── project-status/         # Project status and work streams
├── 01_core_project_info.md # Core project information
├── README.md              # Merged documentation index
└── ssl_setup_readme.md    # (EXISTING) SSL setup guide
```

## Files to be Moved

### Core Documentation Files (backend/docs/ → docs/)
1. `backend/docs/01_core_project_info.md` → `docs/01_core_project_info.md`
2. `backend/docs/README.md` → Will be merged into `docs/README.md`
3. `backend/docs/.DS_Store` → Not migrated (system file)

### API Documentation (backend/docs/api/ → docs/api/)
1. `backend/docs/api/instainstru-api-guide.md` → `docs/api/instainstru-api-guide.md`
2. `backend/docs/api/instainstru-openapi.yaml` → `docs/api/instainstru-openapi.yaml`
3. `backend/docs/api/instainstru-postman.json` → `docs/api/instainstru-postman.json`
4. `backend/docs/api/typescript-interfaces/index.d.ts` → `docs/api/typescript-interfaces/index.d.ts`
5. `backend/docs/api/.DS_Store` → Not migrated (system file)

### Architecture Documentation (backend/docs/architecture/ → docs/architecture/)
1. `backend/docs/architecture/02_architecture_state.md` → `docs/architecture/02_architecture_state.md`
2. `backend/docs/architecture/06_repository_pattern_architecture.md` → `docs/architecture/06_repository_pattern_architecture.md`
3. `backend/docs/architecture/architecture-decisions.md` → `docs/architecture/architecture-decisions.md`
4. `backend/docs/architecture/repository-pattern-implementation.md` → `docs/architecture/repository-pattern-implementation.md`
5. `backend/docs/architecture/service-layer-transformation-report.md` → `docs/architecture/service-layer-transformation-report.md`

### A-Team Deliverables (backend/docs/a-team-deliverables/ → docs/a-team-deliverables/)
1. `backend/docs/a-team-deliverables/adaptive-flow-complete (1).md` → `docs/a-team-deliverables/adaptive-flow-complete (1).md`
2. `backend/docs/a-team-deliverables/adaptive-flow-complete.md` → `docs/a-team-deliverables/adaptive-flow-complete.md`
3. `backend/docs/a-team-deliverables/booking-flows-sketches.md` → `docs/a-team-deliverables/booking-flows-sketches.md`
4. `backend/docs/a-team-deliverables/design-approach-onepager.md` → `docs/a-team-deliverables/design-approach-onepager.md`
5. `backend/docs/a-team-deliverables/final-booking-flow.md` → `docs/a-team-deliverables/final-booking-flow.md`
6. `backend/docs/a-team-deliverables/home-screen-sketch.md` → `docs/a-team-deliverables/home-screen-sketch.md`
7. `backend/docs/a-team-deliverables/home-screen-web-sketch.md` → `docs/a-team-deliverables/home-screen-web-sketch.md`
8. `backend/docs/a-team-deliverables/information-architecture.md` → `docs/a-team-deliverables/information-architecture.md`
9. `backend/docs/a-team-deliverables/instainstru-mood-board.md` → `docs/a-team-deliverables/instainstru-mood-board.md`
10. `backend/docs/a-team-deliverables/instainstru-success-metrics.md` → `docs/a-team-deliverables/instainstru-success-metrics.md`
11. `backend/docs/a-team-deliverables/missing-ui-components.md` → `docs/a-team-deliverables/missing-ui-components.md`
12. `backend/docs/a-team-deliverables/mobile-search-screens.md` → `docs/a-team-deliverables/mobile-search-screens.md`
13. `backend/docs/a-team-deliverables/phoenix-frontend-initiative.md` → `docs/a-team-deliverables/phoenix-frontend-initiative.md`
14. `backend/docs/a-team-deliverables/README.md` → `docs/a-team-deliverables/README.md`
15. `backend/docs/a-team-deliverables/student-booking-implementation-guide.md` → `docs/a-team-deliverables/student-booking-implementation-guide.md`

### Week 3 Designs (backend/docs/a-team-deliverables/week3-designs/ → docs/a-team-deliverables/week3-designs/)
1. `backend/docs/a-team-deliverables/week3-designs/README.md` → `docs/a-team-deliverables/week3-designs/README.md`
2. `backend/docs/a-team-deliverables/week3-designs/homepage-refinements/category-bar-design v12.txt` → `docs/a-team-deliverables/week3-designs/homepage-refinements/category-bar-design v12.txt`
3. `backend/docs/a-team-deliverables/week3-designs/homepage-refinements/homepage-redesign-mockup v13.txt` → `docs/a-team-deliverables/week3-designs/homepage-refinements/homepage-redesign-mockup v13.txt`
4. `backend/docs/a-team-deliverables/week3-designs/homepage-refinements/homepage-review-feedback.txt` → `docs/a-team-deliverables/week3-designs/homepage-refinements/homepage-review-feedback.txt`
5. `backend/docs/a-team-deliverables/week3-designs/homepage-refinements/light-yellow-background-guide.txt` → `docs/a-team-deliverables/week3-designs/homepage-refinements/light-yellow-background-guide.txt`
6. `backend/docs/a-team-deliverables/week3-designs/homepage-refinements/minimal-category-icons.txt` → `docs/a-team-deliverables/week3-designs/homepage-refinements/minimal-category-icons.txt`
7. `backend/docs/a-team-deliverables/week3-designs/homepage-refinements/search-bar-component v9.txt` → `docs/a-team-deliverables/week3-designs/homepage-refinements/search-bar-component v9.txt`
8. `backend/docs/a-team-deliverables/week3-designs/payment-flow/hybrid-payment-mockup.txt` → `docs/a-team-deliverables/week3-designs/payment-flow/hybrid-payment-mockup.txt`
9. `backend/docs/a-team-deliverables/week3-designs/payment-flow/hybrid-technical-requirements.txt` → `docs/a-team-deliverables/week3-designs/payment-flow/hybrid-technical-requirements.txt`
10. `backend/docs/a-team-deliverables/week3-designs/payment-flow/payment-comparison.txt` → `docs/a-team-deliverables/week3-designs/payment-flow/payment-comparison.txt`
11. `backend/docs/a-team-deliverables/week3-designs/payment-flow/payment-flow-diagram.txt` → `docs/a-team-deliverables/week3-designs/payment-flow/payment-flow-diagram.txt`
12. `backend/docs/a-team-deliverables/week3-designs/payment-flow/payment-ui-patterns.txt` → `docs/a-team-deliverables/week3-designs/payment-flow/payment-ui-patterns.txt`
13. `backend/docs/a-team-deliverables/week3-designs/planning/implementation-status-visual.txt` → `docs/a-team-deliverables/week3-designs/planning/implementation-status-visual.txt`
14. `backend/docs/a-team-deliverables/week3-designs/planning/student-flow-todo-list.txt` → `docs/a-team-deliverables/week3-designs/planning/student-flow-todo-list.txt`

### Development Documentation (backend/docs/development/ → docs/development/)
1. `backend/docs/development/setup-guide.md` → `docs/development/setup-guide.md`
2. `backend/docs/development/testing/05_testing_infrastructure.md` → `docs/development/testing/05_testing_infrastructure.md`
3. `backend/docs/development/testing/Test Suite Reorganization Report - Session v61 (Updated v64).md` → `docs/development/testing/Test Suite Reorganization Report - Session v61 (Updated v64).md`

### Infrastructure Documentation (backend/docs/infrastructure/ → docs/infrastructure/)
1. `backend/docs/infrastructure/ssl_implementation_summary.md` → `docs/infrastructure/ssl_implementation_summary.md`
2. `backend/docs/infrastructure/ssl-config-summary.md` → `docs/infrastructure/ssl-config-summary.md`
3. `backend/docs/infrastructure/test-database-safety.md` → `docs/infrastructure/test-database-safety.md`

### Project Status Documentation (backend/docs/project-status/ → docs/project-status/)
1. `backend/docs/project-status/03_work-streams-status.md` → `docs/project-status/03_work-streams-status.md`
2. `backend/docs/project-status/04_system-capabilities.md` → `docs/project-status/04_system-capabilities.md`
3. `backend/docs/project-status/Frontend Technical Debt Cleanup Checklist - Work Stream #13.md` → `docs/project-status/Frontend Technical Debt Cleanup Checklist - Work Stream #13.md`
4. `backend/docs/project-status/InstaInstru Complete State Assessment.md` → `docs/project-status/InstaInstru Complete State Assessment.md`
5. `backend/docs/project-status/updated-todo-priority-list.md` → `docs/project-status/updated-todo-priority-list.md`
6. `backend/docs/project-status/work-streams/Work Stream #10 - Two-Table Availability Design Removal.md` → `docs/project-status/work-streams/Work Stream #10 - Two-Table Availability Design Removal.md`

## Files Staying in Place (Already in /docs/)

1. `docs/development/testing-patterns-doc.md`
2. `docs/flows/analysis/audit-corrections.md`
3. `docs/flows/analysis/component-usage.mmd`
4. `docs/flows/analysis/flow-analysis-summary.md`
5. `docs/flows/independent-audit-results.md`
6. `docs/flows/navigation-map.html`
7. `docs/flows/README.md`
8. `docs/flows/shared/auth-flows.mmd`
9. `docs/flows/student/booking-flow.mmd`
10. `docs/ssl_setup_readme.md`

## Files Requiring Path Updates

These 13 files contain references to `backend/docs/` that need updating:

1. **CLAUDE.md** - Multiple references to backend/docs/ paths
2. **backend/docs/project-status/03_work-streams-status.md** - References to backend/docs/api/
3. **backend/docs/project-status/04_system-capabilities.md** - References to backend/docs/api/ and backend/docs/
4. **backend/docs/project-status/updated-todo-priority-list.md** - References to backend/docs/api/
5. **backend/docs/infrastructure/ssl_implementation_summary.md** - Directory structure showing docs/
6. **backend/docs/a-team-deliverables/week3-designs/README.md** - Multiple references to backend/docs/ locations
7. **backend/docs/development/setup-guide.md** - Links to various backend/docs/ files
8. **monitoring/DEVELOPMENT.md** - External docs URLs (no changes needed)
9. **monitoring/RUNBOOK.md** - External docs URLs (no changes needed)
10. **monitoring/PRODUCTION.md** - External docs URLs (no changes needed)
11. **monitoring/terraform/README.md** - External docs URLs (no changes needed)
12. **frontend/playwright.config.ts** - External docs URLs (no changes needed)
13. **frontend/README.md** - External docs URLs (no changes needed)

**Actual files needing updates**: 7 files (items 1-7 above)

## Special Handling

### README Merge Plan
1. Take existing `docs/flows/README.md` content
2. Merge with `backend/docs/README.md` content
3. Create comprehensive index of all documentation
4. Include navigation guide for new structure

### Post-Migration Tasks
1. Create redirect notice in `/backend/docs/README.md` pointing to new location
2. Update all internal documentation references
3. Update CLAUDE.md with new paths
4. Verify all links work correctly
5. Update any CI/CD scripts that reference documentation paths

## Migration Commands Preview

```bash
# Core files
mv backend/docs/01_core_project_info.md docs/

# API documentation
mv backend/docs/api/* docs/api/

# Architecture documentation
mv backend/docs/architecture/* docs/architecture/

# A-Team deliverables (preserving subdirectories)
cp -r backend/docs/a-team-deliverables/* docs/a-team-deliverables/

# Development documentation
cp -r backend/docs/development/* docs/development/

# Infrastructure documentation
mv backend/docs/infrastructure/* docs/infrastructure/

# Project status documentation
cp -r backend/docs/project-status/* docs/project-status/
```

## Validation Checklist
- [ ] All directories created under /docs/
- [ ] No naming conflicts identified
- [ ] Path update requirements documented
- [ ] README merge plan defined
- [ ] Migration commands tested
- [ ] Rollback plan available
