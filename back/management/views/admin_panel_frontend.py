from django.contrib.auth.decorators import user_passes_test
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.shortcuts import render
from django.http import HttpResponse
from back.utils import CoolerJson
from management.api.user_data import get_user_data
from management.api.user_slug_filter_lookup import get_users_by_slug_filter, get_filter_slug_filtered_users_multiple_paginated
from management.models.user import User
from management import controller
from django.core.paginator import Paginator
import json
from management.models.user import (
    User,
)

from management.models.profile import (
    Profile,
    ProfileSerializer,
)

from management.models.state import (
    StateSerializer,
    State
)


@user_passes_test(lambda u: u.is_staff)
def admin_panel(request):
    """
    This renders our sweet admin matching panel
    We allow it to contain a bunch of 'filters' in the query params
    """
    GET = request.GET
    filters = None
    if GET.getlist("filter"):
        filters = GET.getlist("filter")
    elif GET.get("filter"):
        filters = [GET.get("filter")]
    else:
        filters = ["state.user_form_state:is:filled"]

    user_list_data = []

    bm_user = controller.get_base_management_user()
    extra_info = {
        "filter_options": {
            "profile": ProfileSerializer(bm_user.profile).data["options"],
            "state": StateSerializer(bm_user.state).data["options"],
            # "user": UserSerializer(bm_user).data["options"]
        }
    }
    # It is also possible to pass two selectiosn s1=1&s2=2
    if 'suggest' in GET:
        extra_info['suggest'] = GET['suggest']
        user = controller.get_user_by_hash(GET['suggest'])

        # If we have 's1' we even try to list suggestions
        from ..models.matching_scores import MatchinScore
        suggestions = MatchinScore.matching_suggestion_from_database(user)
        suggested_users = []
        for suggestion in suggestions:
            data = get_user_data(controller.get_user_by_pk(
                int(suggestion["to_usr"])), is_self=True, admin=True)
            suggested_users.append({**data, 'score': suggestion})

        extra_info['suggested_users'] = suggested_users
        extra_info['s1'] = user.hash
        user_list_data = [get_user_data(user, is_self=True, admin=True)]
    elif 'matches' in GET:
        extra_info['matches'] = GET['matches']
        user = controller.get_user_by_hash(GET['matches'])

        # If we have 's1' we even try to list suggestions
        from ..models.matching_scores import MatchinScore

        # TODO: test needs to be updated using the new 'Match' model.
        extra_info['suggested_users'] = [{**get_user_data(
            u, is_self=True, admin=True), "score": []} for u in user.state.matches.all()]
        extra_info['s1'] = user.hash
        user_list_data = [get_user_data(user, is_self=True, admin=True)]
    else:
        user_list_data, _info = get_filter_slug_filtered_users_multiple_paginated(
            filters=filters,
            page=GET.get("page", 1),
            paginate_by=GET.get("paginate_by", 50)
        )
        extra_info.update(_info)

    if 's2' in GET:
        extra_info['s2'] = GET['s2']

    return render(request, "admin_panel_frontend.html",
                  {"user_data": json.dumps({
                      "user_list": user_list_data,
                      "extra_info": extra_info,
                  }, cls=CoolerJson)})


@user_passes_test(lambda u: u.state.has_extra_user_permission("view-stats") or u.is_staff)
def stats_panel(request, regrouped_by="day"):
    """
    Display backend stats
    """
    from tracking.models import Summaries

    print("RENDER STATA")

    all_series = Summaries.objects.filter(
        label=f"time-series-summary-{regrouped_by}").order_by("-time_created").first().meta

    static_stats = Summaries.objects.filter(
        label="static-stats-summary").order_by("-time_created").first().meta

    data = {
        **all_series,
        "static_stats": static_stats
    }

    return render(request, "stats_panel_frontend.html", {
        "stats_data": json.dumps(data)
    })


list_app_stores = {
    "app_activity": "slug:average_call_length_day,loging_count_day,per_match_activity,average_message_amount_per_chat_day",
    "user_groth_stats": "slug:absolute_user_groth_by_day,relative_user_groth_by_day,commulative_user_groth_by_day",

    # From presentation:
    "user_influx": "slug:registration_count_day,growth_change_table_overview,absoulte_user_growth,relative_user_growth_by_day,commulative_user_growth_by_day,weekly_user_growth,learner_vs_volunteers_vs_total_registrations",
    "match_quality": "slug:overall_match_quality_stats,video_call_quality_per_match,chat_quality_per_match,per_match_activity",
    "app_activity": "slug:total_tracking_slots_per_day,matches_made_count_day,average_message_amount_per_chat_day,average_call_length_day,video_calls_held_day,dialogs_active_day,messages_send_day,events_happened_day,loging_count_day",
    "user_profiles": "slug:user_age_distribution,learner_language_level_pie,user_commitment_state_pie,user_interests_pie"
}


@user_passes_test(lambda u: u.state.has_extra_user_permission("view-stats") or u.is_staff)
def graph_panel(request, slug=None):

    if slug == "any":
        slug = "slug:average_message_amount_per_chat_day"
    elif slug.startswith("list:"):
        slug = list_app_stores[slug.split(":")[-1]]

    graph_lookus = []
    graph_data = []
    if slug.startswith("slug:"):
        sd = slug.split(":")[-1]
        if "," in sd:
            graph_lookus = sd.split(",")
        else:
            graph_lookus = [sd]
        for graph_slug in graph_lookus:
            graph_data.append(get_graph(graph_slug))
    elif slug.startswith("hash:"):
        sd = slug.split(":")[-1]
        if "," in sd:
            graph_lookus = sd.split(",")
        else:
            graph_lookus = [sd]
        for graph_hash in graph_lookus:
            graph_data.append(get_graph_hash(graph_hash))

    return render(request, "graph_panel_frontend.html", {
        "graph_data": json.dumps(graph_data)
    })


class FectchGraphSerializer(serializers.Serializer):
    slug = serializers.CharField()

    def create(self, validated_data):
        return validated_data


def get_graph_hash(hash):
    from tracking.models import GraphModel, Summaries

    graph_sum = Summaries.objects.filter(
        label="series-graph-summary-day").order_by("-time_created").first()

    cur_graph = GraphModel.objects.filter(hash=hash).order_by("-time")

    if not cur_graph.exists():
        return HttpResponse(f"Graph for hash '{hash}' not found")

    newest_graph = cur_graph.first()

    return {
        "slug": newest_graph.slug,
        "hash": newest_graph.hash,
        "time": newest_graph.time.isoformat(),
        "oldest_time": cur_graph.last().time.isoformat(),
        "newest_time": newest_graph.time.isoformat(),
        "data": newest_graph.graph_data,
        "slug_options": graph_sum.meta["slugs"],
        "type": newest_graph.type,
        "amount_versions": cur_graph.count()
    }


def get_graph(slug):
    from tracking.models import GraphModel, Summaries

    graph_sum = Summaries.objects.filter(
        label="series-graph-summary-day").order_by("-time_created").first()

    static_sum = Summaries.objects.filter(
        label="static-graph-summary").order_by("-time_created").first()

    cur_graph = GraphModel.objects.filter(slug=slug).order_by("-time")

    if not cur_graph.exists():
        return HttpResponse(f"Graph for slug '{slug}' not found")

    newest_graph = cur_graph.first()

    return {
        "slug": slug,
        "hash": newest_graph.hash,
        "time": newest_graph.time.isoformat(),
        "oldest_time": cur_graph.last().time.isoformat(),
        "newest_time": newest_graph.time.isoformat(),
        "data": newest_graph.graph_data,
        "slug_options": [*graph_sum.meta["slugs"], *static_sum.meta["slugs"]],
        "type": newest_graph.type,
        "amount_versions": cur_graph.count()
    }


@user_passes_test(lambda u: u.state.has_extra_user_permission("view-lists") or u.is_staff)
def user_list_frontend(request):

    user_list_default = "active-user-searching"
    ul, info = get_user_list(user_list_default)

    return render(request, "user_list_frontend.html", {
        "user_list_data": json.dumps({
            "user_lists": [[0]],
            "state": {
                "available_lists": info
            }
        })
    })


class FectchListSerializer(serializers.Serializer):
    label = serializers.CharField()

    def create(self, validated_data):
        return validated_data


def get_user_list(label):
    from tracking.models import Summaries

    sum = Summaries.objects.filter(label="user-list-summary").order_by(
        "-time_created").first()

    ul = sum.meta["detailed_user_listing"][label]

    # Now we got to add some more relevant info about that user
    info = list(sum.meta["detailed_user_listing"].keys())

    return ul, info


@user_passes_test(lambda u: u.state.has_extra_user_permission("view-lists") or u.is_staff)
@api_view(["POST"])
def fetch_list(request):
    serializer = FectchListSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    data = serializer.save()

    list, info = get_user_list(data['label'])

    return Response({
        "user_list": list
    })


@user_passes_test(lambda u: u.state.has_extra_user_permission("view-stats") or u.is_staff)
@api_view(["POST"])
def fetch_graph(request):
    serializer = FectchGraphSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    data = serializer.save()
    graph_data = get_graph(data['slug'])

    return Response(graph_data)
