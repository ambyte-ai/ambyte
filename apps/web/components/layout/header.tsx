"use client";

import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";

export function Header() {
    return (
        <header className="border-b border-border bg-card px-6 h-14 flex items-center justify-between">
            <div className="flex items-center gap-4">
                <OrganizationSwitcher
                    hidePersonal={true} // Force Organization usage
                    afterCreateOrganizationUrl="/"
                    appearance={{
                        elements: {
                            rootBox: "flex items-center",
                            organizationSwitcherTrigger:
                                "h-9 px-3 border border-border rounded-md hover:bg-accent hover:text-accent-foreground transition-colors",
                        },
                    }}
                />
                {/* Breadcrumbs or Project Switcher would go here TODO*/}
            </div>

            <div className="flex items-center gap-4">
                <UserButton
                    appearance={{
                        elements: {
                            avatarBox: "h-8 w-8",
                        },
                    }}
                />
            </div>
        </header>
    );
}
