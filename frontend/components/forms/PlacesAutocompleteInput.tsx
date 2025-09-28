'use client';

import type {
  ChangeEventHandler,
  FocusEventHandler,
  InputHTMLAttributes,
  KeyboardEventHandler,
} from 'react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';

import { cn } from '@/lib/utils';
import { withApiBase } from '@/lib/apiBase';

type PlaceSuggestion = {
  place_id: string;
  description?: string | null;
  text?: string | null;
  types?: string[] | null;
};

interface PlacesAutocompleteInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'> {
  value: string;
  onValueChange: (value: string) => void;
  onSelectSuggestion?: (suggestion: PlaceSuggestion) => void;
  inputClassName?: string;
  containerClassName?: string;
  minQueryLength?: number;
  debounceMs?: number;
  suggestionLimit?: number;
}

const DEFAULT_MIN_QUERY = 3;
const DEFAULT_DEBOUNCE = 250;

export function PlacesAutocompleteInput(props: PlacesAutocompleteInputProps) {
  const {
    value,
    onValueChange,
    onSelectSuggestion,
    inputClassName,
    containerClassName,
    minQueryLength = DEFAULT_MIN_QUERY,
    debounceMs = DEFAULT_DEBOUNCE,
    suggestionLimit = 8,
    disabled,
    onBlur,
    onFocus,
    onKeyDown,
    autoComplete,
    ...inputProps
  } = props;

  const inputRef = useRef<HTMLInputElement | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipNextRef = useRef(false);
  const isMountedRef = useRef(true);

  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState<number>(-1);

  const listboxId = useId();

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (disabled) {
      setSuggestions([]);
      setOpen(false);
      setLoading(false);
      return;
    }

    const trimmed = value.trim();

    if (trimmed.length === 0) {
      setSuggestions([]);
      setOpen(false);
      setLoading(false);
      return;
    }

    if (trimmed.length < minQueryLength) {
      setSuggestions([]);
      setOpen(false);
      setLoading(false);
      return;
    }

    if (skipNextRef.current) {
      skipNextRef.current = false;
      return;
    }

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    const abortController = new AbortController();
    setLoading(true);

    debounceRef.current = setTimeout(async () => {
      try {
        const url = withApiBase(`/api/addresses/places/autocomplete?q=${encodeURIComponent(trimmed)}`);
        const response = await fetch(url, {
          method: 'GET',
          credentials: 'include',
          signal: abortController.signal,
        });

        if (!response.ok) {
          setSuggestions([]);
          setOpen(false);
          return;
        }

        const data = await response.json();
        const items = Array.isArray(data?.items) ? data.items : [];

        const normalized: PlaceSuggestion[] = items
          .map((item: Record<string, unknown>) => {
            const placeId = typeof item['place_id'] === 'string' ? item['place_id'] : undefined;
            const description = typeof item['description'] === 'string' ? item['description'] : null;
            const text = typeof item['text'] === 'string' ? item['text'] : null;
            const types = Array.isArray(item['types']) ? (item['types'] as string[]) : null;

            return placeId
              ? {
                  place_id: placeId,
                  description,
                  text,
                  types,
                }
              : null;
          })
          .filter((item: PlaceSuggestion | null): item is PlaceSuggestion => item !== null)
          .slice(0, suggestionLimit);

        setSuggestions(normalized);
        setHighlightIndex(-1);
        setOpen(normalized.length > 0);
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          return;
        }
        setSuggestions([]);
        setOpen(false);
      } finally {
        if (isMountedRef.current) {
          setLoading(false);
        }
      }
    }, debounceMs);

    return () => {
      abortController.abort();
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [value, disabled, minQueryLength, debounceMs, suggestionLimit]);

  const getDisplayText = useMemo(
    () =>
      (suggestion: PlaceSuggestion) =>
        (suggestion.description || suggestion.text || '').trim(),
    []
  );

  const handleChange: ChangeEventHandler<HTMLInputElement> = (event) => {
    if (disabled) return;
    setOpen(true);
    onValueChange(event.target.value);
  };

  const handleSelect = (suggestion: PlaceSuggestion) => {
    const text = getDisplayText(suggestion);
    skipNextRef.current = true;
    onValueChange(text || value);
    onSelectSuggestion?.(suggestion);
    setOpen(false);
    setSuggestions([]);
    setHighlightIndex(-1);
    // restore focus to input for accessibility
    requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
  };

  const handleInputFocus: FocusEventHandler<HTMLInputElement> = (event) => {
    if (suggestions.length > 0) {
      setOpen(true);
    }
    if (onFocus) {
      onFocus(event);
    }
  };

  const handleInputBlur: FocusEventHandler<HTMLInputElement> = (event) => {
    // Delay closing to allow click events on suggestions
    setTimeout(() => {
      setOpen(false);
      setHighlightIndex(-1);
    }, 120);
    if (onBlur) {
      onBlur(event);
    }
  };

  const handleInputKeyDown: KeyboardEventHandler<HTMLInputElement> = (event) => {
    if (onKeyDown) {
      onKeyDown(event);
    }

    if (!open || suggestions.length === 0) {
      return;
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlightIndex((prev) => (prev + 1) % suggestions.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlightIndex((prev) => {
        const next = prev - 1;
        return next < 0 ? suggestions.length - 1 : next;
      });
    } else if (event.key === 'Enter') {
      if (highlightIndex >= 0 && highlightIndex < suggestions.length) {
        event.preventDefault();
        const suggestion = suggestions[highlightIndex];
        if (suggestion) {
          handleSelect(suggestion);
        }
      }
    } else if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
      setHighlightIndex(-1);
    }
  };

  return (
    <div className={cn('relative', containerClassName)}>
      <input
        {...inputProps}
        ref={inputRef}
        value={value}
        onChange={handleChange}
        onFocus={handleInputFocus}
        onBlur={handleInputBlur}
        onKeyDown={handleInputKeyDown}
        disabled={disabled}
        autoComplete={autoComplete ?? 'off'}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listboxId}
        role="combobox"
        className={cn(
          'w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:border-purple-500 focus:ring-2 focus:ring-[#7E22CE]/10 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-500',
          inputClassName
        )}
      />
      {open && suggestions.length > 0 && (
        <div
          id={listboxId}
          role="listbox"
          className="absolute z-20 mt-2 w-full overflow-hidden rounded-lg border border-gray-200 bg-white shadow-lg"
        >
          {suggestions.map((suggestion, index) => {
            const displayText = getDisplayText(suggestion);
            if (!displayText) return null;
            const isHighlighted = index === highlightIndex;
            return (
              <button
                key={suggestion.place_id}
                type="button"
                role="option"
                aria-selected={isHighlighted}
                className={cn(
                  'flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-purple-50 focus:bg-purple-50',
                  isHighlighted && 'bg-purple-50'
                )}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => handleSelect(suggestion)}
              >
                <span className="truncate">{displayText}</span>
              </button>
            );
          })}
        </div>
      )}
      {loading && (
        <div className="pointer-events-none absolute right-10 top-1/2 -translate-y-1/2 text-xs text-gray-400">
          Loading…
        </div>
      )}
    </div>
  );
}

export type { PlaceSuggestion };
