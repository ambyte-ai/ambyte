import { redirect } from "next/navigation";

export default function RootPage() {
    // Redirect the root URL "/" immediately to "/dashboard"
    redirect("/dashboard");
}