"use client";

import { Filter, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";

interface InventoryToolbarProps {
	searchQuery: string;
	onSearchChange: (query: string) => void;
	platformFilter: string;
	onPlatformChange: (platform: string) => void;
	sensitivityFilter: string;
	onSensitivityChange: (sensitivity: string) => void;
}

const PLATFORMS = [
	{ value: "all", label: "All Platforms" },
	{ value: "snowflake", label: "Snowflake" },
	{ value: "databricks", label: "Databricks" },
	{ value: "aws-s3", label: "AWS S3" },
	{ value: "postgres", label: "PostgreSQL" },
];

const SENSITIVITIES = [
	{ value: "all", label: "All Sensitivities" },
	{ value: "PUBLIC", label: "Public" },
	{ value: "INTERNAL", label: "Internal" },
	{ value: "CONFIDENTIAL", label: "Confidential" },
	{ value: "RESTRICTED", label: "Restricted" },
	{ value: "UNSPECIFIED", label: "Unspecified" },
];

export function InventoryToolbar({
	searchQuery,
	onSearchChange,
	platformFilter,
	onPlatformChange,
	sensitivityFilter,
	onSensitivityChange,
}: InventoryToolbarProps) {
	// Local state for debouncing the search input
	const [localQuery, setLocalQuery] = useState(searchQuery);

	// Sync local query if parent changes it (e.g., via clear filters)
	useEffect(() => {
		setLocalQuery(searchQuery);
	}, [searchQuery]);

	// Debounce the search input by 300ms to avoid API spam
	useEffect(() => {
		const timer = setTimeout(() => {
			if (localQuery !== searchQuery) {
				onSearchChange(localQuery);
			}
		}, 300);

		return () => clearTimeout(timer);
	}, [localQuery, searchQuery, onSearchChange]);

	const hasFilters =
		localQuery !== "" ||
		platformFilter !== "all" ||
		sensitivityFilter !== "all";

	const handleClearFilters = () => {
		setLocalQuery("");
		onSearchChange("");
		onPlatformChange("all");
		onSensitivityChange("all");
	};

	return (
		<div className="flex flex-col gap-4 sm:flex-row sm:items-center">
			{/* Search Input */}
			<div className="relative flex-1">
				<Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
				<Input
					placeholder="Search inventory by URN or Name..."
					className="pl-9 bg-card border-border/50 focus-visible:ring-primary/50 transition-all shadow-sm"
					value={localQuery}
					onChange={(e) => setLocalQuery(e.target.value)}
				/>
			</div>

			{/* Filters */}
			<div className="flex flex-wrap items-center gap-2">
				{/* Platform Filter */}
				<Select value={platformFilter} onValueChange={onPlatformChange}>
					<SelectTrigger className="w-[160px] bg-card border-border/50 shadow-sm">
						<Filter className="mr-2 h-3.5 w-3.5 opacity-70" />
						<SelectValue placeholder="Platform" />
					</SelectTrigger>
					<SelectContent>
						{PLATFORMS.map((platform) => (
							<SelectItem key={platform.value} value={platform.value}>
								{platform.label}
							</SelectItem>
						))}
					</SelectContent>
				</Select>

				{/* Sensitivity Filter */}
				<Select value={sensitivityFilter} onValueChange={onSensitivityChange}>
					<SelectTrigger className="w-[160px] bg-card border-border/50 shadow-sm">
						<Filter className="mr-2 h-3.5 w-3.5 opacity-70" />
						<SelectValue placeholder="Sensitivity" />
					</SelectTrigger>
					<SelectContent>
						{SENSITIVITIES.map((level) => (
							<SelectItem key={level.value} value={level.value}>
								{level.label}
							</SelectItem>
						))}
					</SelectContent>
				</Select>

				{/* Clear Filters Button */}
				{hasFilters && (
					<Button
						variant="ghost"
						size="sm"
						onClick={handleClearFilters}
						className="h-9 px-2 text-muted-foreground hover:text-foreground hover:bg-muted/50"
					>
						<X className="h-4 w-4 mr-1" />
						Clear
					</Button>
				)}
			</div>
		</div>
	);
}
