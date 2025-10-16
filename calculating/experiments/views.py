import json
from datetime import datetime, timezone as tz

from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from .forms import ExperimentImportForm, ExperimentSelectForm
from .models import Experiment


# ----------------- сервисные заглушки (заменишь своей логикой) -----------------

def post_save_configs(exp: Experiment) -> None:
    """Заглушка: действия после сохранения конфигов (лог, проверка, постановка задачи и т.д.)."""
    pass

def run_calculation(exp: Experiment, run_dt, period: str):
    """
    Заглушка: запуск расчётов.
    run_dt — aware datetime (или None), period — одно из: selected_date / from_selected_to_yesterday / all_time.
    Должна вернуть (cohort_filled: bool, calculation_finished: bool).
    """
    return True, True


# ----------------- вспомогательные утилиты -----------------

PERIOD_CHOICES = {"selected_date", "from_selected_to_yesterday", "all_time"}

def redirect_with_state(exp_id, finished: bool):
    """Возвращаемся на дашборд, сохраняя выбранный фильтр и эксперимент."""
    return redirect(f"{reverse('exp_dashboard')}?finished={'1' if finished else '0'}&experiment={exp_id}")

def build_context(request, finished: bool):
    """Готовим контекст для рендера страницы (список, выбранный эксперимент, formatted JSON и дата)."""
    qs = Experiment.objects.all()
    if not finished:
        qs = qs.filter(calculation_finished=False)

    select_form = ExperimentSelectForm(
        data={'finished': finished, 'experiment': request.GET.get('experiment')}
    )
    select_form.fields['experiment'].queryset = qs.order_by('name')

    exp = None
    segments_pretty = ''
    funnels_pretty = ''
    date_value = ''

    exp_id = request.GET.get('experiment')
    if exp_id:
        try:
            exp = qs.get(pk=exp_id)
            segments_pretty = json.dumps(exp.config_segments, ensure_ascii=False, indent=2)
            funnels_pretty = json.dumps(exp.config_funnels, ensure_ascii=False, indent=2)
            dt_local = exp.last_update_date.astimezone(timezone.get_current_timezone())
            date_value = dt_local.strftime('%Y-%m-%dT%H:%M')  # для <input type="datetime-local">
        except Experiment.DoesNotExist:
            exp = None

    return {
        'form': ExperimentImportForm(),
        'select_form': select_form,
        'finished': finished,
        'exp': exp,
        'segments_pretty': segments_pretty,
        'funnels_pretty': funnels_pretty,
        'date_value': date_value,
    }


# ----------------- основное view -----------------

@require_http_methods(["GET", "POST"])
def dashboard(request):
    # 1) читаем флаг фильтра один раз
    finished_param = request.POST.get('finished') or request.GET.get('finished')
    finished = (finished_param == '1')

    # 2) SAVE
    if request.method == "POST" and 'save' in request.POST:
        exp = get_object_or_404(Experiment, pk=request.POST.get('experiment_id'))

        try:
            exp.config_segments = json.loads(request.POST.get('config_segments', '{}'))
            exp.config_funnels = json.loads(request.POST.get('config_funnels', '{}'))
        except json.JSONDecodeError as e:
            messages.error(request, f"Некорректный JSON в конфиге: {e}")
            return redirect_with_state(exp.pk, finished)

        exp.save()
        post_save_configs(exp)
        messages.success(request, "Сохранено")
        return redirect_with_state(exp.pk, finished)

    # 3) RUN
    if request.method == "POST" and 'run' in request.POST:
        exp = get_object_or_404(Experiment, pk=request.POST.get('experiment_id'))

        # дата
        date_str = request.POST.get('date')
        try:
            if date_str:
                naive = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
                run_dt = timezone.make_aware(naive, timezone.get_current_timezone())
            else:
                run_dt = timezone.now()
        except ValueError as e:
            messages.error(request, f"Некорректная дата: {e}")
            return redirect_with_state(exp.pk, finished)

        # период
        period = request.POST.get('period', 'selected_date')
        if period not in PERIOD_CHOICES:
            messages.error(request, "Некорректное значение периода")
            return redirect_with_state(exp.pk, finished)

        # запуск заглушки
        cohort_filled, calculation_finished = run_calculation(exp, run_dt, period)

        # правило обновления даты: ставим выбранную (или now, если не задана)
        exp.last_update_date = run_dt
        exp.cohort_filled = bool(cohort_filled)
        exp.calculation_finished = bool(calculation_finished)
        exp.save()

        messages.success(request, "Расчёты запущены")
        return redirect_with_state(exp.pk, finished)

    # 4) IMPORT
    if request.method == "POST" and 'import' in request.POST:
        form = ExperimentImportForm(request.POST, request.FILES)
        if not form.is_valid():
            messages.error(request, "Загрузите файл или вставьте JSON")
            # показываем страницу со всеми блоками
            return render(request, "experiments/dashboard.html", build_context(request, finished))

        # источник данных
        if form.cleaned_data.get('json_file'):
            raw_bytes = form.cleaned_data['json_file'].read()
            raw_text = raw_bytes.decode('utf-8', errors='replace')
        else:
            raw_text = form.cleaned_data.get('json_text', '')

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as e:
            messages.error(request, f"Некорректный JSON: {e}")
            return render(request, "experiments/dashboard.html", build_context(request, finished))

        required = {
            "id", "name", "config_segments", "config_funnels",
            "last_update_date", "stopped", "cohort_filled", "calculation_finished"
        }
        missing = required - set(payload.keys())
        if missing:
            messages.error(request, f"В JSON отсутствуют поля: {', '.join(sorted(missing))}")
            return render(request, "experiments/dashboard.html", build_context(request, finished))

        # простая проверка типов для конфигов
        if not isinstance(payload["config_segments"], dict) or not isinstance(payload["config_funnels"], dict):
            messages.error(request, "config_segments и config_funnels должны быть объектами JSON")
            return render(request, "experiments/dashboard.html", build_context(request, finished))

        try:
            dt = datetime.fromtimestamp(payload["last_update_date"], tz=tz.utc)  # aware UTC
        except Exception as e:
            messages.error(request, f"last_update_date не распознан как UNIX timestamp: {e}")
            return render(request, "experiments/dashboard.html", build_context(request, finished))

        defaults = {
            "name": payload["name"],
            "config_segments": payload["config_segments"],
            "config_funnels": payload["config_funnels"],
            "last_update_date": dt,
            "stopped": bool(payload["stopped"]),
            "cohort_filled": bool(payload["cohort_filled"]),
            "calculation_finished": bool(payload["calculation_finished"]),
        }

        obj, created = Experiment.objects.update_or_create(pk=payload["id"], defaults=defaults)
        messages.success(request, "Эксперимент создан" if created else "Эксперимент обновлён")
        return redirect_with_state(obj.pk, finished)

    # 5) GET: отрисовать страницу
    context = build_context(request, finished)
    return render(request, "experiments/dashboard.html", context)
