import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** The selected snapshot lives in the URL (`?snapshot=`), so a board view can be shared and reloaded. */
export function useSnapshotParam(): [string | undefined, (id: string | undefined) => void] {
  const [params, setParams] = useSearchParams();
  const value = params.get("snapshot") ?? undefined;
  const set = useCallback(
    (id: string | undefined) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (id === undefined) next.delete("snapshot");
          else next.set("snapshot", id);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );
  return [value, set];
}
