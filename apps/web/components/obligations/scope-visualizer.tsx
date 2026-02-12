import { Ban, Globe, Tag } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ResourceSelector } from "@/types/obligation";

interface ScopeVisualizerProps {
	selector: ResourceSelector;
	className?: string;
}

export function ScopeVisualizer({ selector, className }: ScopeVisualizerProps) {
	const hasTags =
		selector.match_tags && Object.keys(selector.match_tags).length > 0;
	const hasIncludes =
		selector.include_patterns && selector.include_patterns.length > 0;
	const hasExcludes =
		selector.exclude_patterns && selector.exclude_patterns.length > 0;

	return (
		<div className={cn("flex flex-col gap-6", className)}>
			{/* Tags Section */}
			<div>
				<div className="flex items-center gap-2 mb-3">
					<Tag className="h-4 w-4 text-muted-foreground" />
					<span className="text-sm font-medium text-muted-foreground">
						Resource Tags
					</span>
				</div>

				{hasTags ? (
					<div className="flex flex-wrap gap-2">
						{Object.entries(selector.match_tags).map(([key, value]) => (
							<Badge
								key={`${key}-${value}`}
								variant="secondary"
								className="px-2 py-1 gap-1.5 text-xs bg-muted/50 border-muted-foreground/20 hover:bg-muted/80 text-foreground"
							>
								<span className="font-semibold opacity-70">{key}:</span>
								{value}
							</Badge>
						))}
					</div>
				) : (
					<p className="text-sm text-muted-foreground italic pl-6">
						No tag filters applied.
					</p>
				)}
			</div>

			{/* Patterns Section */}
			<div className="grid gap-4 md:grid-cols-2">
				{/* Include Patterns */}
				<div className="rounded-lg border bg-card text-card-foreground shadow-sm">
					<div className="flex items-center gap-2 p-3 border-b bg-muted/40">
						<Globe className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
						<h3 className="font-medium text-sm">Included Patterns</h3>
						<span className="ml-auto text-xs text-muted-foreground">
							{selector.include_patterns?.length || 0}
						</span>
					</div>
					{hasIncludes ? (
						<div className="p-0">
							<ul className="divide-y text-sm">
								{selector.include_patterns.map((pattern, i) => (
									<li
										key={i}
										className="px-3 py-2 font-mono text-xs bg-muted/10 break-all"
									>
										{pattern}
									</li>
								))}
							</ul>
						</div>
					) : (
						<div className="p-4 text-center text-xs text-muted-foreground italic">
							No include patterns defined (Matches all by default?)
						</div>
					)}
				</div>

				{/* Exclude Patterns */}
				<div className="rounded-lg border bg-card text-card-foreground shadow-sm">
					<div className="flex items-center gap-2 p-3 border-b bg-muted/40">
						<Ban className="h-4 w-4 text-rose-600 dark:text-rose-400" />
						<h3 className="font-medium text-sm">Excluded Patterns</h3>
						<span className="ml-auto text-xs text-muted-foreground">
							{selector.exclude_patterns?.length || 0}
						</span>
					</div>
					{hasExcludes ? (
						<div className="p-0">
							<ul className="divide-y text-sm">
								{selector.exclude_patterns.map((pattern, i) => (
									<li
										key={i}
										className="px-3 py-2 font-mono text-xs text-muted-foreground bg-muted/10 break-all"
									>
										{pattern}
									</li>
								))}
							</ul>
						</div>
					) : (
						<div className="p-4 text-center text-xs text-muted-foreground italic">
							No exclude patterns defined.
						</div>
					)}
				</div>
			</div>
		</div>
	);
}
