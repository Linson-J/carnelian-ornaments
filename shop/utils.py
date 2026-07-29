from django.utils.text import slugify


def unique_slug(instance, source_value, queryset, slug_field='slug'):
    base_slug = slugify(source_value) or 'item'
    slug = base_slug
    index = 1

    while queryset.filter(**{slug_field: slug}).exclude(pk=instance.pk).exists():
        slug = f'{base_slug}-{index}'
        index += 1

    return slug
