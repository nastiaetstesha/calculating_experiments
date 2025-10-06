import json
from datetime import datetime, timezone as tz

from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from .forms import ExperimentImportForm, ExperimentSelectForm
from django.utils import timezone
from .models import Experiment


@require_http_methods(["GET", "POST"])
def dashboard(request):
    if request.method == "POST" and 'import' in request.POST:
        form = ExperimentImportForm(request.POST, request.FILES)

        if not form.is_valid():
            messages.error(request, "Загрузите файл или вставьте JSON")
            return render(request, "experiments/dashboard.html", {"form": form})

        # 1) получить «сырое» содержимое
        if form.cleaned_data.get('json_file'):
            # файл -> bytes -> str
            raw_bytes = form.cleaned_data['json_file'].read()
            raw_text = raw_bytes.decode('utf-8', errors='replace')
        else:
            raw_text = form.cleaned_data.get('json_text', '')

        try:
            # 2) распарсить JSON в dict
            payload = json.loads(raw_text)
        except json.JSONDecodeError as e:
            messages.error(request, f"Некорректный JSON: {e}")
            return render(request, "experiments/dashboard.html", {"form": form})

        # 3) базовая схема — проверяем ключи (минимум)
        required = {"id", "name", "config_segments", "config_funnels", "last_update_date", "stopped", "cohort_filled", "calculation_finished"}
        missing = required - set(payload.keys())
        if missing:
            messages.error(request, f"в JSON отсутствуют поля: {', '.join(sorted(missing))}")
            return render(request, "experiments/dashboard.html", {"form": form})

        # 4) конвертация last_update_date
        #    в примере приходит UNIX timestamp (секунды)
        try:
            dt = datetime.fromtimestamp(payload["last_update_date"], tz=tz.utc)
        except Exception as e:
            messages.error(request, f"last_update_date не распознан как UNIX timestamp: {e}")
            return render(request, "experiments/dashboard.html", {"form": form})

        # 5) подготовить defaults для update_or_create
        defaults = {
            "name": payload["name"],
            "config_segments": payload["config_segments"],
            "config_funnels": payload["config_funnels"],
            "last_update_date": dt,
            "stopped": bool(payload["stopped"]),
            "cohort_filled": bool(payload["cohort_filled"]),
            "calculation_finished": bool(payload["calculation_finished"]),
        }

        # 6) создать или обновить запись
        #    pk=payload['id'] — потому что у тебя primary_key=True на id
        obj, created = Experiment.objects.update_or_create(
            pk=payload["id"],
            defaults=defaults
        )

        messages.success(
            request,
            "Эксперимент создан" if created else "Эксперимент обновлён"
        )
        return redirect("exp_dashboard")
    
    finished = request.GET.get('finished') == '1'   # ← вот твой finished (bool)

    qs = Experiment.objects.all()
    if not finished:
        qs = qs.filter(calculation_finished=False)

    # Форма выбора с текущими значениями из GET
    select_form = ExperimentSelectForm(
        data={'finished': finished, 'experiment': request.GET.get('experiment')}
    )
    select_form.fields['experiment'].queryset = qs.order_by('name')

    # Если выбран experiment — подгружаем его и готовим данные для отображения
    exp = None
    segments_pretty = ''
    funnels_pretty = ''
    date_value = ''

    if request.GET.get('experiment'):
        try:
            exp = qs.get(pk=request.GET['experiment'])
            segments_pretty = json.dumps(exp.config_segments, ensure_ascii=False, indent=2)
            funnels_pretty  = json.dumps(exp.config_funnels,  ensure_ascii=False, indent=2)
            dt = exp.last_update_date.astimezone(timezone.get_current_timezone())
            date_value = dt.strftime('%Y-%m-%dT%H:%M')  # для <input type="datetime-local">
        except Experiment.DoesNotExist:
            exp = None

    context = {
        'form': ExperimentImportForm(),  # старая форма импорта
        'select_form': select_form,
        'finished': finished,
        'exp': exp,
        'segments_pretty': segments_pretty,
        'funnels_pretty': funnels_pretty,
        'date_value': date_value,
    }
    return render(request, "experiments/dashboard.html", context)
    # # GET-запрос — просто показать форму
    # form = ExperimentImportForm()
    # return render(request, "experiments/dashboard.html", {"form": form})
