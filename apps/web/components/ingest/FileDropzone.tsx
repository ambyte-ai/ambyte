"use client";

import { FileText, Sparkles, UploadCloud, X } from "lucide-react";
import type React from "react";
import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface FileDropzoneProps {
	onUpload: (file: File) => void;
	isUploading: boolean;
	className?: string;
}

export function FileDropzone({
	onUpload,
	isUploading,
	className,
}: FileDropzoneProps) {
	const [isDragging, setIsDragging] = useState(false);
	const [selectedFile, setSelectedFile] = useState<File | null>(null);
	const [error, setError] = useState<string | null>(null);

	const fileInputRef = useRef<HTMLInputElement>(null);

	// Helper to format bytes to MB/KB
	const formatFileSize = (bytes: number) => {
		if (bytes === 0) return "0 Bytes";
		const k = 1024;
		const sizes = ["Bytes", "KB", "MB", "GB"];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return Number.parseFloat((bytes / k ** i).toFixed(2)) + " " + sizes[i];
	};

	const validateAndSetFile = (file: File) => {
		setError(null);
		if (file.type !== "application/pdf") {
			setError("Invalid file type. Please upload a PDF document.");
			return;
		}
		// Optional: Add size limit check here if needed (e.g., 20MB)
		// if (file.size > 20 * 1024 * 1024) { ... } TODO

		setSelectedFile(file);
	};

	// --- Drag and Drop Handlers ---
	const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		e.stopPropagation();
		setIsDragging(true);
	}, []);

	const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		e.stopPropagation();
		setIsDragging(false);
	}, []);

	const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
		e.preventDefault();
		e.stopPropagation();
		setIsDragging(false);

		const files = e.dataTransfer.files;
		if (files && files.length > 0) {
			validateAndSetFile(files[0]);
		}
	}, []);

	const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
		const files = e.target.files;
		if (files && files.length > 0) {
			validateAndSetFile(files[0]);
		}
	};

	const clearFile = () => {
		setSelectedFile(null);
		setError(null);
		if (fileInputRef.current) {
			fileInputRef.current.value = "";
		}
	};

	return (
		<Card
			className={cn(
				"relative overflow-hidden transition-all duration-300 border-2",
				isDragging
					? "border-indigo-500 bg-indigo-500/5 shadow-[0_0_30px_-5px_rgba(99,102,241,0.3)]"
					: "border-border/50 border-dashed bg-gradient-to-br from-zinc-900/50 to-zinc-950/50 hover:border-indigo-500/50 hover:bg-zinc-900/80",
				className,
			)}
			onDragOver={handleDragOver}
			onDragLeave={handleDragLeave}
			onDrop={handleDrop}
		>
			<div className="p-8 md:p-12 flex flex-col items-center justify-center text-center min-h-[300px]">
				{/* STATE 1: No file selected */}
				{!selectedFile && (
					<>
						<div
							className={cn(
								"mb-6 flex h-20 w-20 items-center justify-center rounded-full transition-all duration-300",
								isDragging
									? "bg-indigo-500/20 text-indigo-400 scale-110"
									: "bg-muted/50 text-muted-foreground",
							)}
						>
							<UploadCloud className="h-10 w-10" />
						</div>

						<h3 className="mb-2 text-xl font-semibold tracking-tight text-foreground">
							Upload Legal Document
						</h3>
						<p className="mb-6 max-w-sm text-sm text-muted-foreground leading-relaxed">
							Drag and drop your Data Processing Agreement (DPA) or Master
							Services Agreement (MSA) here.
						</p>

						<Button
							type="button"
							variant="outline"
							onClick={() => fileInputRef.current?.click()}
							className="border-indigo-500/30 text-indigo-400 hover:bg-indigo-500/10 hover:text-indigo-300"
						>
							Browse Files
						</Button>

						{error && (
							<p className="mt-4 text-sm font-medium text-rose-500 animate-in fade-in slide-in-from-bottom-2">
								{error}
							</p>
						)}
					</>
				)}

				{/* STATE 2: File selected, ready to upload */}
				{selectedFile && (
					<div className="w-full max-w-md animate-in fade-in zoom-in-95 duration-300">
						<div className="mb-8 flex items-center gap-4 rounded-xl border border-border/50 bg-background/50 p-4 shadow-sm backdrop-blur-sm">
							<div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400">
								<FileText className="h-6 w-6" />
							</div>
							<div className="flex flex-1 flex-col overflow-hidden text-left">
								<span className="truncate font-medium text-foreground">
									{selectedFile.name}
								</span>
								<span className="text-xs text-muted-foreground">
									{formatFileSize(selectedFile.size)} • PDF Document
								</span>
							</div>
							<Button
								type="button"
								variant="ghost"
								size="icon"
								onClick={clearFile}
								disabled={isUploading}
								className="shrink-0 text-muted-foreground hover:text-rose-500"
							>
								<X className="h-4 w-4" />
							</Button>
						</div>

						<Button
							type="button"
							size="xl"
							onClick={() => onUpload(selectedFile)}
							disabled={isUploading}
							className="w-full gap-2 bg-gradient-to-r from-indigo-500 to-violet-600 hover:from-indigo-600 hover:to-violet-700 text-white shadow-lg shadow-indigo-500/25 transition-all"
						>
							{isUploading ? (
								<>
									<UploadCloud className="h-5 w-5 animate-pulse" />
									Initializing Pipeline...
								</>
							) : (
								<>
									<Sparkles className="h-5 w-5" />
									Extract Policies
								</>
							)}
						</Button>
					</div>
				)}

				{/* Hidden file input */}
				<input
					type="file"
					ref={fileInputRef}
					onChange={handleFileInput}
					accept="application/pdf"
					className="hidden"
				/>
			</div>
		</Card>
	);
}
