"use client";

import { Check, Copy, ShieldCheck, Terminal } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePublicKey } from "@/hooks/use-audit-config";
import { cn } from "@/lib/utils";

export function AuditConfig() {
    const { publicKey, isLoading, isError } = usePublicKey();
    const [isCopied, setIsCopied] = useState(false);

    const cliSnippet = publicKey
        ? `export AMBYTE_SYSTEM_PUBLIC_KEY="${publicKey}"\nambyte audit verify <log-id>`
        : "";

    const handleCopyCommand = async () => {
        if (!cliSnippet) return;
        await navigator.clipboard.writeText(cliSnippet);
        setIsCopied(true);
        setTimeout(() => setIsCopied(false), 2000);
    };

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Header Section */}
            <div>
                <h3 className="text-lg font-medium text-foreground">
                    Audit Integrity
                </h3>
                <p className="text-sm text-muted-foreground">
                    Cryptographic keys used to secure and verify your policy
                    enforcement ledger.
                </p>
            </div>

            {/* Card 1: System Public Key */}
            <Card className="border-border/50 shadow-sm bg-card/50 overflow-hidden">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <ShieldCheck className="h-5 w-5 text-emerald-400" />
                        System Public Key
                    </CardTitle>
                    <CardDescription className="leading-relaxed max-w-2xl">
                        Ambyte seals audit logs into immutable blocks using an
                        Ed25519 private key. Use the public key below to
                        mathematically verify the integrity of your logs via the
                        CLI.
                    </CardDescription>
                </CardHeader>

                <CardContent className="space-y-5">
                    {isLoading ? (
                        <Skeleton className="h-[160px] w-full rounded-xl bg-muted/50" />
                    ) : isError ? (
                        <div className="text-sm text-rose-500 font-medium bg-rose-500/10 border border-rose-500/20 p-4 rounded-lg">
                            Failed to load public key. Please try again later.
                        </div>
                    ) : (
                        <>
                            {/* Stylized Terminal Block */}
                            <div className="rounded-xl border border-zinc-800 bg-[#0D0D0D] shadow-2xl overflow-hidden ring-1 ring-white/5">
                                {/* Fake Window Header */}
                                <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-800 bg-zinc-900/80">
                                    <div className="flex items-center gap-3">
                                        <div className="flex gap-1.5">
                                            <div className="h-2.5 w-2.5 rounded-full bg-rose-500/50" />
                                            <div className="h-2.5 w-2.5 rounded-full bg-amber-500/50" />
                                            <div className="h-2.5 w-2.5 rounded-full bg-emerald-500/50" />
                                        </div>
                                        <div className="flex items-center gap-2 text-xs font-mono text-zinc-500">
                                            <Terminal className="h-3 w-3" />
                                            <span>ambyte audit verify</span>
                                        </div>
                                    </div>

                                    {/* Copy CLI Command Button */}
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={handleCopyCommand}
                                        className={cn(
                                            "h-7 gap-1.5 text-[11px] font-mono transition-colors",
                                            isCopied
                                                ? "text-emerald-400 hover:text-emerald-400"
                                                : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
                                        )}
                                    >
                                        {isCopied ? (
                                            <>
                                                <Check className="h-3 w-3" />
                                                Copied!
                                            </>
                                        ) : (
                                            <>
                                                <Copy className="h-3 w-3" />
                                                Copy CLI command
                                            </>
                                        )}
                                    </Button>
                                </div>

                                {/* Terminal Content */}
                                <div className="p-4 space-y-1.5 font-mono text-[11px] leading-relaxed">
                                    {/* Line 1: comment */}
                                    <div className="text-zinc-600">
                                        # Set the system public key for local verification
                                    </div>

                                    {/* Line 2: export */}
                                    <div className="flex flex-wrap gap-x-1">
                                        <span className="text-indigo-400">export</span>
                                        <span className="text-zinc-300">
                                            AMBYTE_SYSTEM_PUBLIC_KEY=
                                        </span>
                                        <span className="text-emerald-400 break-all">
                                            &quot;{publicKey}&quot;
                                        </span>
                                    </div>

                                    {/* Line 3: blank */}
                                    <div className="h-2" />

                                    {/* Line 4: comment */}
                                    <div className="text-zinc-600">
                                        # Verify any audit log by its UUID
                                    </div>

                                    {/* Line 5: command */}
                                    <div className="flex gap-1">
                                        <span className="text-cyan-400">ambyte</span>
                                        <span className="text-zinc-300">audit verify</span>
                                        <span className="text-amber-400/70">
                                            &lt;log-id&gt;
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* Subtle hint */}
                            <p className="text-[12px] text-muted-foreground/70 leading-relaxed">
                                This key is derived from the Ambyte system signing
                                key and cannot be changed. It is safe to share —
                                it can only <em>verify</em> signatures, not create
                                them.
                            </p>
                        </>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
