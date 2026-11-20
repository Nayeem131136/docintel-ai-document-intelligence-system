import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { EmptyState } from "../components/ui";

export default function NotFound() {
  return (
    <EmptyState icon={<Compass className="h-6 w-6" />} title="Page not found" hint="The page you are looking for does not exist."
      action={<Link className="text-sm font-medium text-accent-700 underline" to="/">Back to the dashboard</Link>} />
  );
}
