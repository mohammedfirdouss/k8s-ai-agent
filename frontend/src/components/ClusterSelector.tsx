"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { getClusters } from "@/services/api";

type ClusterSelectorProps = {
  selected: string | null;
  onSelect: (cluster: string) => void;
  disabled: boolean;
};

// Lists the kubeconfig contexts as selectable pills. The parent owns the
// selection; `onSelect` fires once with the default (current context or the
// first cluster) as soon as the list loads.
export default function ClusterSelector({
  selected,
  onSelect,
  disabled,
}: ClusterSelectorProps) {
  const { data, isError } = useQuery({
    queryKey: ["clusters"],
    queryFn: getClusters,
    retry: false,
  });

  const clusters = data?.clusters ?? [];

  // Default selection: backend's current context, else the first cluster.
  useEffect(() => {
    if (selected || clusters.length === 0) return;
    const fallback =
      data?.current && clusters.includes(data.current)
        ? data.current
        : clusters[0];
    onSelect(fallback);
  }, [selected, clusters, data, onSelect]);

  if (isError || (data && (clusters.length === 0 || data.error))) {
    return (
      <p className="text-xs text-slate-400">
        No clusters found in kubeconfig — using default context
      </p>
    );
  }

  if (!data) return null;

  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        Cluster
      </h3>
      <div className="mt-2 flex flex-wrap gap-2">
        {clusters.map((cluster) => {
          const isSelected = cluster === selected;
          return (
            <button
              key={cluster}
              type="button"
              onClick={() => onSelect(cluster)}
              disabled={disabled && !isSelected}
              className={
                isSelected
                  ? "rounded-full bg-slate-900 px-4 py-1.5 text-sm font-medium text-white"
                  : "rounded-full border border-slate-300 px-4 py-1.5 text-sm text-slate-700 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
              }
            >
              {cluster}
            </button>
          );
        })}
      </div>
    </div>
  );
}
