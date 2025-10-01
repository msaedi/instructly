"""Legacy helper retired after service area refactor."""

if __name__ == "__main__":
    raise RuntimeError(
        "Obsolete script: 'areas_of_service' has been removed. "
        "Use InstructorServiceAreaRepository.replace_areas(...) to seed/update service areas."
    )
