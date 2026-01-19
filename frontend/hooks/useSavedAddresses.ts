import type { UseQueryResult } from '@tanstack/react-query';

import { useUserAddresses } from '@/hooks/queries/useUserAddresses';
import { formatMeetingLocation } from '@/utils/address/format';
import type { AddressListResponse, AddressResponse } from '@/src/api/generated/instructly.schemas';

export type SavedAddress = AddressResponse;

type UseSavedAddressesResult = UseQueryResult<AddressListResponse> & {
  addresses: SavedAddress[];
};

export function useSavedAddresses(enabled: boolean = true): UseSavedAddressesResult {
  const query = useUserAddresses(enabled);
  const addresses = query.data?.items ?? [];
  return { ...query, addresses };
}

export function formatAddress(address: SavedAddress): string {
  const line1 = [address.street_line1, address.street_line2].filter(Boolean).join(', ');
  return formatMeetingLocation(
    line1,
    address.locality,
    address.administrative_area,
    address.postal_code
  );
}

export function getAddressLabel(address: SavedAddress): string {
  const label = (address.label ?? '').toString().trim().toLowerCase();
  if (label === 'other') {
    const custom = address.custom_label ? address.custom_label.toString().trim() : '';
    return custom.length > 0 ? custom : 'Other';
  }
  if (label === 'home' || label === 'work') {
    return label.charAt(0).toUpperCase() + label.slice(1);
  }
  return 'Other';
}
