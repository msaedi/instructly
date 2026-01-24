import {
  useSavedAddresses,
  formatAddress,
  getAddressLabel,
  type SavedAddress,
} from '@/hooks/useSavedAddresses';
import { useServiceAreaCheck } from '@/hooks/useServiceAreaCheck';

interface AddressSelectorProps {
  instructorId: string;
  locationType: 'student_location' | 'neutral_location';
  selectedAddress: SavedAddress | null;
  onSelectAddress: (address: SavedAddress | null) => void;
  onEnterNewAddress: () => void;
}

export function AddressSelector({
  instructorId,
  locationType,
  selectedAddress,
  onSelectAddress,
  onEnterNewAddress,
}: AddressSelectorProps) {
  const { addresses: savedAddresses, isLoading } = useSavedAddresses();

  const selectedLat =
    selectedAddress && typeof selectedAddress.latitude === 'number'
      ? selectedAddress.latitude
      : undefined;
  const selectedLng =
    selectedAddress && typeof selectedAddress.longitude === 'number'
      ? selectedAddress.longitude
      : undefined;

  const { data: serviceAreaCheck } = useServiceAreaCheck({
    instructorId,
    lat: selectedLat,
    lng: selectedLng,
  });

  if (isLoading) {
    return <div className="text-sm text-gray-500">Loading addresses...</div>;
  }

  const hasAddresses = savedAddresses.length > 0;

  return (
    <div className="space-y-3">
      <label className="text-sm font-medium text-gray-700">
        {locationType === 'student_location'
          ? 'Where should the instructor come?'
          : 'Where would you like to meet?'}
      </label>

      {hasAddresses ? (
        <div className="space-y-2">
          {savedAddresses.map((address) => (
            <AddressOption
              key={address.id}
              address={address}
              isSelected={selectedAddress?.id === address.id}
              onSelect={() => onSelectAddress(address)}
              instructorId={instructorId}
            />
          ))}

          <button
            type="button"
            onClick={onEnterNewAddress}
            className="text-sm text-[#7E22CE] hover:text-[#7E22CE] hover:underline"
          >
            + Use a different address
          </button>
        </div>
      ) : (
        <div>
          <p className="text-sm text-gray-500 mb-2">
            No saved addresses. Enter an address below or save one in your profile.
          </p>
          <button
            type="button"
            onClick={onEnterNewAddress}
            className="text-sm text-[#7E22CE] hover:text-[#7E22CE] hover:underline"
          >
            Enter address
          </button>
        </div>
      )}

      {selectedAddress && serviceAreaCheck?.is_covered === false && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          This address is outside the instructor&#39;s service area. Please choose a different
          address or book an online lesson.
        </div>
      )}
    </div>
  );
}

interface AddressOptionProps {
  address: SavedAddress;
  isSelected: boolean;
  onSelect: () => void;
  instructorId: string;
}

function AddressOption({ address, isSelected, onSelect, instructorId }: AddressOptionProps) {
  const lat = typeof address.latitude === 'number' ? address.latitude : undefined;
  const lng = typeof address.longitude === 'number' ? address.longitude : undefined;
  const hasCoords = lat !== undefined && lng !== undefined;
  const { data: areaCheck, isLoading } = useServiceAreaCheck({
    instructorId,
    lat,
    lng,
  });

  const isCovered = hasCoords ? areaCheck?.is_covered ?? true : false;
  const isDisabled = !hasCoords || (!isLoading && !isCovered);

  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={isDisabled}
      className={`w-full p-3 text-left border rounded-lg transition-colors ${
        isSelected ? 'border-[#7E22CE] bg-purple-50' : 'border-gray-200'
      } ${isDisabled ? 'opacity-50 cursor-not-allowed' : 'hover:border-gray-300'}`}
    >
      <div className="flex items-center justify-between">
        <div>
          <span className="font-medium">{getAddressLabel(address)}</span>
          {address.is_default && (
            <span className="ml-2 text-xs bg-gray-100 px-2 py-0.5 rounded">Default</span>
          )}
        </div>
        {!hasCoords && (
          <span className="text-xs text-red-500">Missing coordinates</span>
        )}
        {hasCoords && !isCovered && (
          <span className="text-xs text-red-500">Not in service area</span>
        )}
      </div>
      <p className="text-sm text-gray-600 mt-1">{formatAddress(address)}</p>
    </button>
  );
}
