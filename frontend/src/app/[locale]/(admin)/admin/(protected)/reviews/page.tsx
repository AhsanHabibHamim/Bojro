import { ReviewModeration } from "@/components/admin/reviews/review-moderation";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminReviewsRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <ReviewModeration locale={locale as AppLocale} />;
}
