from django.db import models


class Experiment(models.Model):
    id = models.PositiveIntegerField(primary_key=True)
    name = models.CharField('Название', max_length=100, unique=True)
    config_segments = models.JSONField('Перечень сегментов расчёта', default=dict)
    config_funnels = models.JSONField('Перечень воронок расчёта', default=dict)
    last_update_date = models.DateTimeField('Обновлён', auto_now=True)
    stopped = models.BooleanField(
        'Остановлен',
        default=False,
        db_index=True
        )
    cohort_filled = models.BooleanField(
        'Дошли все данные',
        default=False,
        db_index=True
        )
    calculation_finished = models.BooleanField(
        'Выполнены все расчёты',
        default=False,
        db_index=True
        )

    class Meta:
        verbose_name = 'Эксперимент'
        verbose_name_plural = 'Эксперименты'
        ordering = ['-last_update_date']

    def __str__(self):
        if self.user:
            return self.user.get_username()
        return f'{self.name} (#{self.pk})'