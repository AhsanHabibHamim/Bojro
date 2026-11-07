import { ContentEditor } from "@/components/admin/content/content-editor";
import type { AppLocale } from "@/i18n/routing";

export default async function NewBlogPostRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <ContentEditor id={null} kind="blog" locale={locale as AppLocale} />;
}
