type AccountSetupCompletionInput = {
  hasProfilePicture: boolean;
  firstName: string | null | undefined;
  lastName: string | null | undefined;
  postalCode: string | null | undefined;
  phoneVerified: boolean;
  bio: string | null | undefined;
  hasServiceArea: boolean;
  requiresTeachingLocation: boolean;
  hasTeachingLocation: boolean;
};

export function isAccountSetupComplete({
  hasProfilePicture,
  firstName,
  lastName,
  postalCode,
  phoneVerified,
  bio,
  hasServiceArea,
  requiresTeachingLocation,
  hasTeachingLocation,
}: AccountSetupCompletionInput): boolean {
  return (
    hasProfilePicture &&
    Boolean(firstName?.trim()) &&
    Boolean(lastName?.trim()) &&
    Boolean(postalCode?.trim()) &&
    phoneVerified &&
    String(bio || '').trim().length >= 400 &&
    hasServiceArea &&
    (!requiresTeachingLocation || hasTeachingLocation)
  );
}
