import { AlertOctagon, Eye, HelpCircle, UserCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ENFORCEMENT_LABELS, EnforcementLevel } from "@/types/obligation";

interface EnforcementBadgeProps {
	level: EnforcementLevel;
	className?: string;
	showIcon?: boolean;
}

export function EnforcementBadge({
	level,
	className,
	showIcon = true,
}: EnforcementBadgeProps) {
	// Define semantic styles for each level
	// Using Tailwind utility classes for color mapping
	const styles = {
		[EnforcementLevel.BLOCKING]: {
			variant: "destructive" as const,
			icon: AlertOctagon,
			// Solid red for maximum visibility
			classes:
				"bg-rose-500/15 text-rose-500 hover:bg-rose-500/25 border-rose-500/20",
		},
		[EnforcementLevel.AUDIT_ONLY]: {
			variant: "secondary" as const,
			icon: Eye,
			// Amber/Yellow for warning/observation
			classes:
				"bg-amber-500/15 text-amber-500 hover:bg-amber-500/25 border-amber-500/20",
		},
		[EnforcementLevel.NOTIFY_HUMAN]: {
			variant: "default" as const,
			icon: UserCheck,
			// Blue/Indigo for informational/process
			classes:
				"bg-indigo-500/15 text-indigo-500 hover:bg-indigo-500/25 border-indigo-500/20",
		},
		[EnforcementLevel.UNSPECIFIED]: {
			variant: "outline" as const,
			icon: HelpCircle,
			// Muted grey for unknown
			classes: "text-muted-foreground bg-muted/30 border-border",
		},
	};

	const config = styles[level] || styles[EnforcementLevel.UNSPECIFIED];
	const Icon = config.icon;

	return (
		<Badge
			variant="outline"
			className={cn(
				"gap-1.5 px-2 py-0.5 font-medium border transition-colors",
				config.classes,
				className,
			)}
		>
			{showIcon && <Icon className="h-3.5 w-3.5" strokeWidth={2} />}
			<span className="text-[11px] uppercase tracking-wide">
				{ENFORCEMENT_LABELS[level]}
			</span>
		</Badge>
	);
}
