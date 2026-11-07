import { ContentEditor } from "@/components/admin/content/content-editor";
import type { AppLocale } from "@/i18n/routing";

export default async function BlogPostEditorRoute({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  return <ContentEditor id={id} kind="blog" locale={locale as AppLocale} />;
}
