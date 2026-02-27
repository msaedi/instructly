# iNSTAiNSTRU Documentation

Welcome to the iNSTAiNSTRU documentation. This guide helps you navigate all project documentation, now consolidated under `/docs/`.

## 📁 Documentation Structure

### 🎯 [Project Overview](./project-overview/)
- [Core Project Information](./project-overview/01_core_project_info.md) - Mission, priorities, and team structure

### 🏗️ [Architecture](./architecture/)
- [Architecture State](./architecture/02_architecture_state.md) - Current system architecture
- [Repository Pattern Architecture](./architecture/06_repository_pattern_architecture.md) - Repository implementation patterns
- [Codebase Structure](./07_codebase_structure.md) - Directory structure and navigation guide
- [Architecture Decisions](./architecture/architecture-decisions.md) - Key design choices
- [Repository Pattern Implementation](./architecture/repository-pattern-implementation.md) - Implementation details
- [Service Layer Transformation Report](./architecture/service-layer-transformation-report.md) - Service refactoring details

### 📊 [Project Status](./project-status/)
- [Work Streams Status](./project-status/03_work-streams-status.md) - Active work stream progress
- [System Capabilities](./project-status/04_system-capabilities.md) - What's working and what's not
- [Frontend Technical Debt Cleanup](./project-status/Frontend%20Technical%20Debt%20Cleanup%20Checklist%20-%20Work%20Stream%20%2313.md) - Critical frontend refactoring
- [Complete State Assessment](./project-status/InstaInstru%20Complete%20State%20Assessment.md) - Full system assessment
- [Updated Todo Priority List](./project-status/updated-todo-priority-list.md) - Current priorities
- [Work Streams](./project-status/work-streams/) - Detailed work stream documentation

### 🎨 [A-Team Deliverables](./a-team-deliverables/)
Design team deliverables and mockups:
- [Student Booking Implementation Guide](./a-team-deliverables/student-booking-implementation-guide.md) - 6-8 week implementation plan
- [Missing UI Components](./a-team-deliverables/missing-ui-components.md) - Required UI components
- [Week 3 Designs](./a-team-deliverables/week3-designs/) - Latest design iterations
  - Homepage refinements
  - Payment flow mockups
  - Planning documents

### 📡 [API Documentation](./api/)
- [API Endpoint Reference](./api/09_api_endpoints.md) - Complete endpoint reference (333 endpoints)
- [API Usage Guide](./api/instainstru-api-guide.md) - Complete endpoint documentation
- [OpenAPI Specification](./api/instainstru-openapi.yaml) - Machine-readable API spec
- [Postman Collection](./api/instainstru-postman.json) - Import into Postman

### 💻 [Development](./development/)
- [Setup Guide](./development/setup-guide.md) - Getting started locally
- [Testing Patterns](./development/testing-patterns-doc.md) - Testing best practices
- [Testing Infrastructure](./development/testing/05_testing_infrastructure.md) - Test suite architecture
- [Test Suite Reorganization Report](./development/testing/Test%20Suite%20Reorganization%20Report%20-%20Session%20v61%20(Updated%20v64).md)

### 🔧 [Infrastructure](./infrastructure/)
- [External Service Integrations](./10_external_integrations.md) - Complete mapping of all external services
- [SSL Implementation Summary](./infrastructure/ssl_implementation_summary.md) - HTTPS setup overview
- [SSL Configuration Summary](./infrastructure/ssl-config-summary.md) - SSL configuration details
- [Test Database Safety](./infrastructure/test-database-safety.md) - Protecting production data
- [SSL Setup README](./ssl_setup_readme.md) - Quick SSL setup guide

### 🔄 [User Flows](./flows/)
- [Flow Analysis](./flows/analysis/) - User flow analysis and corrections
- [Navigation Map](./flows/navigation-map.html) - Visual navigation structure
- [Authentication Flows](./flows/shared/auth-flows.md) - Auth flow diagrams
- [Student Booking Flow](./flows/student/booking-flow.md) - Booking process flow

## 🚀 Quick Start

1. **New to the project?** Start with [Core Project Information](./project-overview/01_core_project_info.md)
2. **Navigating the codebase?** See [Codebase Structure](./07_codebase_structure.md) for directory layout
3. **Setting up locally?** Follow the [Setup Guide](./development/setup-guide.md)
4. **Understanding the architecture?** Read [Architecture State](./architecture/02_architecture_state.md)
5. **Working on student features?** Check [Student Booking Implementation Guide](./a-team-deliverables/student-booking-implementation-guide.md)

## 📋 Document Organization

The documentation follows a logical structure where numbered files (01-10) are distributed by topic:
- **01** - Project overview documentation
- **02** - Architecture documentation
- **03, 04** - Project status documentation
- **05** - Testing documentation
- **06** - Architecture patterns documentation
- **07** - Codebase structure documentation
- **09** - API endpoint reference
- **10** - External service integrations

## 🔍 Finding Information

- **Backend Development**: Check `/architecture/` and `/development/`
- **Frontend Development**: See `/a-team-deliverables/` for designs and `/project-status/` for technical debt
- **API Integration**: Browse `/api/` for specifications
- **Infrastructure**: Look in `/infrastructure/` for deployment and SSL
- **User Experience**: Review `/flows/` for user journey maps

## 📝 Contributing to Documentation

When adding new documentation:
1. Place it in the appropriate category directory
2. Update this README with links to new documents
3. Follow the existing naming conventions
4. Include last updated dates in your documents

## Migration Notice

This documentation was migrated from `/backend/docs/` on July 17, 2025. All paths have been updated to reflect the new structure.
