import { useEffect, useRef, useState } from "react";

import { SearchField } from "./SearchField";

type DebouncedSearchFieldProps = {
  committedValue: string;
  onCommit: (value: string) => void;
  label: string;
  placeholder: string;
  busy?: boolean;
  delay?: number;
};

export function DebouncedSearchField({
  committedValue,
  onCommit,
  label,
  placeholder,
  busy = false,
  delay = 320,
}: DebouncedSearchFieldProps) {
  const [inputValue, setInputValue] = useState(committedValue);
  const [observedCommittedValue, setObservedCommittedValue] =
    useState(committedValue);
  const timeoutRef = useRef<number | null>(null);
  const onCommitRef = useRef(onCommit);

  if (committedValue !== observedCommittedValue) {
    setObservedCommittedValue(committedValue);
    setInputValue(committedValue);
  }

  useEffect(() => {
    onCommitRef.current = onCommit;
  }, [onCommit]);

  useEffect(() => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, [committedValue]);

  useEffect(
    () => () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
    },
    [],
  );

  return (
    <SearchField
      busy={busy || inputValue.trim() !== committedValue}
      label={label}
      onChange={(value) => {
        setInputValue(value);
        if (timeoutRef.current !== null) {
          window.clearTimeout(timeoutRef.current);
        }
        timeoutRef.current = window.setTimeout(() => {
          timeoutRef.current = null;
          const trimmedValue = value.trim();
          setInputValue(trimmedValue);
          onCommitRef.current(trimmedValue);
        }, delay);
      }}
      onClear={() => {
        if (timeoutRef.current !== null) {
          window.clearTimeout(timeoutRef.current);
          timeoutRef.current = null;
        }
        setInputValue("");
        onCommitRef.current("");
      }}
      placeholder={placeholder}
      value={inputValue}
    />
  );
}
