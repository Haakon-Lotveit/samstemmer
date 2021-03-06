# encoding: utf-8
#from fylkesperspektiv.models import Representanter, Sporsmal, Fylker, Personer, Komiteer, Votering, Voteringsresultat, Saker, Wnominateanalyser, Wnominateanalyserposisjoner, Lix, Holmgang, Partilikhet, Fylkeikhet
from samstemmer.fylkesperspektiv.models import *
# from fylkesperspektiv.models import * # ? ville ikke det være like lurt? 

from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.utils import simplejson # if the returned json is odd: http://stackoverflow.com/questions/6286192/using-json-in-django-template
from django.http import HttpResponse
from django.db.models import Count
from django.db.models import Q

#from django.core import serializers

from django.core.serializers.json import DjangoJSONEncoder
import json
import re
import csv
import datetime
import inspect  # to check if a something is of type class.

from collections import defaultdict
from operator import itemgetter

from django.core.context_processors import csrf     #https://docs.djangoproject.com/en/1.3/ref/contrib/csrf/#ajax


import functions        # dette er min function.py fil
from itertools import chain


from django.template.defaultfilters import slugify


from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from django.views.decorators.csrf import csrf_exempt # to define views that is not protected by csrf


#import pdb; pdb.set_trace()     # http://stackoverflow.com/questions/1118183/how-to-debug-in-django-the-good-way



def normalize_query(query_string,
                    findterms=re.compile(r'"([^"]+)"|(\S+)').findall,
                    normspace=re.compile(r'\s{2,}').sub):
    ''' http://julienphalip.com/post/2825034077/adding-search-to-a-django-site-in-a-snap
        Splits the query string in invidual keywords, getting rid of unecessary spaces
        and grouping quoted words together.
        Example:
        
        >>> normalize_query('  some random  words "with   quotes  " and   spaces')
        ['some', 'random', 'words', 'with quotes', 'and', 'spaces']
    
    '''
    return [normspace(' ', (t[0] or t[1]).strip()) for t in findterms(query_string)] 

def get_query(query_string, search_fields):
    ''' Returns a query, that is a combination of Q objects. That combination
        aims to search keywords within a model by testing the given search fields.
    
    '''
    query = None # Query to search for every search term        
    terms = normalize_query(query_string)
    for term in terms:
        or_query = None # Query to search for a given term in each field
        for field_name in search_fields:
            q = Q(**{"%s__icontains" % field_name: term})
            if or_query is None:
                or_query = q
            else:
                or_query = or_query | q
        if query is None:
            query = or_query
        else:
            query = query & or_query
    return query

def search(request):
    query_string = ''
    found_entries = None
    if ('q' in request.GET) and request.GET['q'].strip():
        query_string = request.GET['q']
        
        entry_query = get_query(query_string, ['fornavn', 'etternavn',])

        found_entries = Personer.objects.filter(entry_query) #.order_by('-pub_date')

    dagens = Representanter.objects.filter(dagens_representant=True).values('person')
    random_name = Personer.objects.filter(id__in=dagens).order_by('?').select_related()[0] 

        #random_name = Representanter.objects.filter(dagens_representant=True).order_by('?').select_related()[0]

    return render_to_response('fylkesperspektiv/search_results.html',
                          { 'query_string': query_string, 'found_entries': found_entries, 'random_name':random_name }
                          ) #,context_instance=RequestContext(request))


def oppmote(request, year=None):
    '''rangere folk etter oppmøte'''
    if year:
        y = str(year) #print sesjon
    else:
        y = Sesjoner.objects.get(er_innevaerende=1)
        y = str(y.til).split("-")[0]
        y = int(y)-1     # for at vi skal få med alle voteringene fra årey y må vi sette datoen til siste dag året før:
    
    print y

    # hent dagens
    # current_reps = Representanter.objects.values('person').filter(dagens_representant=1)
    # current_personer = Personer.objects.filter(pk__in=[p['person'] for p in current_reps]).select_related()

    # rep_stats = {}
    # for r in current_personer:
    #     stats = Voteringsresultat.objects.filter(representant_id=r.id).values('votering_avgitt').annotate(Count('votering_avgitt')).select_related()
    #     rep_stats[r.id] = {}
    #     rep_stats[r.id]['stats'] = {'person': r}

    #     for n in stats:
    #         #print n, n['votering_avgitt'], n['votering_avgitt__count']
    #         rep_stats[r.id]['stats'][n['votering_avgitt']] = n['votering_avgitt__count']

    #     try:
    #         is_for =  rep_stats[r.id]['stats']['for']
    #     except:
    #         is_for = 0
    #     try:
    #         is_mot = rep_stats[r.id]['stats']['mot']
    #     except:
    #         is_mot = 0
    #     rep_stats[r.id]['stats']['for_mot'] = '%s/%s' % (is_for, is_mot)
        
    sql = '''SELECT representant_id_id, votering_avgitt, count(votering_avgitt) as c, v.id, p.fornavn, p.etternavn, p.parti_id
            FROM `fylkesperspektiv_voteringsresultat` v, `fylkesperspektiv_votering` vo, `fylkesperspektiv_personer` p
            WHERE vo.votering_tid > '%s-12-31 23:59:59' AND  v.votering_id = vo.votering_id AND v.representant_id_id = p.id
            GROUP BY v.votering_avgitt, v.representant_id_id 
            ORDER BY representant_id_id, votering_avgitt
        ''' % (y)
    resultat = Voteringsresultat.objects.raw(sql)

    rep_stats = {}
    for r in resultat:
        # print r.c, r.votering_avgitt, r.representant_id_id
        # if this is the first loop for this mp, create key
        if r.representant_id_id not in rep_stats:
            rep_stats[r.representant_id_id] = {'p':r.parti_id}
            rep_stats[r.representant_id_id]['navn'] = r.fornavn +' '+ r.etternavn
            rep_stats[r.representant_id_id]['sum'] = 0
        
        rep_stats[r.representant_id_id][r.votering_avgitt] = r.c
        rep_stats[r.representant_id_id]['sum'] += r.c

    #print rep_stats

    years = Votering.objects.raw('SELECT Year(votering_tid) as y, votering_id from fylkesperspektiv_votering group by y order by y desc ')
    years = [int(yy.y)-1 for yy in years]
    return render_to_response('fylkesperspektiv/oppmote.html', {'rep_stats':rep_stats, 'y':str(y), 'years': years })


def index(request):
    fylker = Fylker.objects.all()
    current_reps = Representanter.objects.select_related()    #??

    #current_reps = Dagensrepresentanter.objects.all().select_related()  #.order_by('fylke')#[:5]  

    siste_sporsmal = Sporsmal.objects.all().order_by('-datert_dato')[:2]
    siste_saker = Saker.objects.all().order_by('-sist_oppdatert_dato')[:10]

    nyeste_analyse_id = Wnominateanalyser.objects.values('id').latest('dato')

    dagens = Representanter.objects.filter(dagens_representant=True).values('person')
    random_name = Personer.objects.filter(id__in=dagens).order_by('?').select_related()[0] 
    
    #return render_to_response('fylkesperspektiv/index.html', {'siste_saker':siste_saker, 'siste_sporsmal':siste_sporsmal, 'current_reps': current_reps, 'fylker': fylker })
    return render_to_response('fylkesperspektiv/index.html', {'nyeste_analyse_id':nyeste_analyse_id, 'siste_saker':siste_saker, 'siste_sporsmal':siste_sporsmal, 'current_reps': current_reps, 'fylker': fylker,'random_name':random_name })

def metode(request):
    return render_to_response('fylkesperspektiv/metode.html')


def nysgjerrigper(request,  sesjon=None):
    if sesjon:
        s = sesjon #print sesjon
        
    else:
        s = Sesjoner.objects.get(er_innevaerende=1)

    results = Sporsmal.objects.filter(sesjonid=s).values(
        'sporsmal_til_id', 'sporsmal_til_id__fornavn', 'sporsmal_til_id__etternavn', 'sporsmal_til_id__parti', 'sporsmal_til_id__fylke__navn',
        'sporsmal_fra_id', 'sporsmal_fra_id__fornavn', 'sporsmal_fra_id__etternavn', 'sporsmal_fra_id__parti', 'sporsmal_fra_id__fylke__navn' ).annotate(value=Count('sporsmal_fra')).order_by('-value')
#    results = Sporsmal.objects.filter(sesjonid='2012-2013').extra(select={'target': 'sporsmal_til_id', 'source': 'sporsmal_fra_id'}).values('target', 'source').annotate(value=Count('sporsmal_fra'))
    sesjoner = Sesjoner.objects.all().order_by('-id')
    return render_to_response('fylkesperspektiv/nysgjerrigper.html', {'result_sesjon':s,'results':results, 'sesjoner':sesjoner})    







def lix(request):
    # get lix of all current mps
    inner_query = Representanter.objects.filter(dagens_representant=True).values('person')
    #print len(inner_query)
    lix_list = Lix.objects.filter(person__in=inner_query).order_by('-value').select_related(depth=2) 
    #print len(lix_list)
    return render_to_response('fylkesperspektiv/lix.html', {'lix_list': lix_list})

def nedlastinger2(request, hva):
    print hva
    if hva == 'sporsmal':
        sporsmal = Sporsmal.objects.all().order_by('-id')[:200]#.select_related()
        return export(sporsmal)
    elif hva == 'resultat':
        voteringsresultat = Voteringsresultat.objects.all().order_by('-votering__sak')[:507] # 3*169
        return export(voteringsresultat)
    elif hva == 'dagensrep':
        dagens = Personer.objects.filter(id__in=Representanter.objects.all().filter(dagens_representant=True).values("person")).order_by("fylke") #.values('fornavn', 'etternavn', 'foedselsdato', 'doedsdato', 'kjoenn', 'fylke_id', 'parti_id')#.exclude('top_words_in_questions','top_tfidf_words_in_questions')
        #print dagens
        return export(dagens)


def export(qs, fields=None):
    model = qs.model
    response = HttpResponse(mimetype='text/csv')
    response['Content-Disposition'] = 'attachment; filename=%s-%s.csv' % (slugify(model.__name__), len(qs))
    writer = csv.writer(response)
    # Write headers to CSV file
    if fields:
        headers = fields
    else:
        headers = []
        for field in model._meta.fields:
            headers.append(field.name)
    writer.writerow(headers)
    # Write data to CSV file
    ok_types=['int', 'float','long', 'NoneType', 'datetime.datetime', 'unicode']
    for obj in qs:
        row = []
        for field in headers:
            if field in headers:
                val = getattr(obj, field)
                #print val, type(val)
                if callable(val):
                    val = val()
                    print "\t Her: ", val, type(val)
                # work around csv unicode limitation
                if type(val) == unicode:
                    val = val.encode('latin-1', errors='replace')#"utf-8")
                # desperate hack to force convert classes unicode rep into text
                elif val not in ok_types:
                    #print "ja!" * 100
                    val = unicode(val).encode('latin-1', errors='replace')
                print inspect.isclass(val)
                row.append(val)
        writer.writerow(row)
    # Return CSV file to browser as download
    return response

def nedlastinger(request):
    # sporsmal = Sporsmal.objects.all().order_by('-id')[:200]#.select_related()
    # response = HttpResponse(content_type='text/csv')
    # response['Content-Disposition'] = 'attachment; filename="somefilename.csv"'
    # writer = csv.writer(response)
    # for s in sporsmal:
    #     writer.writerow([s.id, 
    #     s.sesjonid, 
    #     unicode(s.besvart_av).encode('latin-1'), 
    #     unicode(s.besvart_av_minister_id).encode('latin-1'),
    #     unicode(s.besvart_av_minister_tittel).encode('latin-1'), 
    #     s.besvart_dato,
    #     unicode(s.besvart_pa_vegne_av).encode('latin-1'),
    #     unicode(s.besvart_pa_vegne_av_minister_id).encode('latin-1'),
    #     unicode(s.besvart_pa_vegne_av_minister_tittel).encode('latin-1'),
    #     s.datert_dato,
    #     s.flyttet_til,
    #     unicode(s.fremsatt_av_annen).encode('latin-1'),
    #     unicode(s.rette_vedkommende).encode('latin-1'),
    #     s.rette_vedkommende_minister_id,
    #     unicode(s.rette_vedkommende_minister_tittel).encode('latin-1'),
    #     s.sendt_dato,
    #     unicode(s.sporsmal_fra).encode('latin-1'),
    #     s.sporsmal_nummer,
    #     unicode(s.sporsmal_til).encode('latin-1'),
    #     s.sporsmal_til_minister_id,
    #     unicode(s.sporsmal_til_minister_tittel).encode('latin-1'),
    #     s.status,
    #     s.type,
    #     unicode(s.tittel).encode('utf-8')
    #     ])#['First row', 'Foo', 'Bar', 'Baz'])
    # return response
    return render_to_response('fylkesperspektiv/nedlastinger.html')


def person_detail(request, rep_id):
    #print rep_id, type(rep_id)
    #p = get_object_or_404(Personer, id=rep_id)
    sf = Sporsmal.objects.filter(sporsmal_fra=rep_id).order_by('-sendt_dato').select_related()#[:5]
    st = Sporsmal.objects.filter(sporsmal_til=rep_id).order_by('-sendt_dato').select_related()#[:5]

    # Voteringsresultat
    # Sporsmal til/fra (til/fra sine egne?)

    fylkeikhet = Fylkeikhet.objects.filter(person=rep_id).order_by('-prosentlikhet')
    partilikhet = Partilikhet.objects.filter(person=rep_id).order_by('-prosentlikhet')
    holmgang = Holmgang.objects.filter(deltager1=rep_id).exclude(prosentlikhet__isnull=True).order_by('-prosentlikhet').select_related()

    #KomiteeMedlemskap
    rep = Representanter.objects.filter(person=rep_id).order_by('-stortingsperiode__til').select_related()
    # Representanter er rep nå? Har vært før?
    # person.top_words_in_questions
    # person.top_tfidf_words_in_questions
    try:
        lix = Lix.objects.get(person=rep_id)
    except:
        lix = None

    person = Personer.objects.get(pk=rep_id)
    v = Voteringsresultat.objects.filter(representant_id=rep_id).select_related()
    v_tilstede = Voteringsresultat.objects.filter(representant_id=rep_id).exclude(votering_avgitt='ikke_tilstede').select_related()
    show_up = 0
    try:
        for a in v:
            if a.votering_avgitt != 'ikke_tilstede':
                show_up+=1
        deltegelse = round(show_up/float(len(v))*100, 1)
    except:
        deltegelse = None

    # oc ?
    nyeste_analyse_id = Wnominateanalyser.objects.values('id').latest('dato')
    #oc = Wnominateanalyserposisjoner.objects.values('representant', 'analyse', 'representant__parti__id', "representant__fylke__navn", "representant__fornavn", "representant__etternavn").filter(analyse=analyse_id)

    return render_to_response('fylkesperspektiv/person_detail.html', {'nyeste_analyse_id':nyeste_analyse_id, 'fylkeikhet':fylkeikhet, 'partilikhet':partilikhet, 'holmgang':holmgang, 'deltegelse':deltegelse, 'lix':lix, 'rep': rep, 'sf': sf, 'st': st, 'person': person, 'v': v, 'v_tilstede': v_tilstede})
    #return render_to_response('fylkesperspektiv/person_detail.html', {'rep': p, 'sf': sf, 'person': person}, context_instance=RequestContext(request))





def fylke(request, fylke_id):
    # dette går ikke fordi person i representanter classen ikke er en ref til person
    #dagens = Representanter.objects.filter(person__fylke=fylke_id)
    query = "SELECT * FROM fylkesperspektiv_representanter, fylkesperspektiv_personer p WHERE person = p.id AND p.fylke_id = '%s' ORDER BY stortingsperiode_id DESC" % fylke_id
    dagens = Representanter.objects.raw(query)
    rep = Personer.objects.filter(fylke=fylke_id)
    # stemmlikhet
    
    # siste 10 avtemninger, "våre" folks stemmer, (resultat)
    return render_to_response('fylkesperspektiv/fylke_detail.html', { 'rep': rep, 'dagens': dagens}) 

def sak(request):
    # dette burde være en graf av noe slag...
    saker = Saker.objects.all().order_by('-sist_oppdatert_dato')
    return render_to_response('fylkesperspektiv/sak.html', {'saker': saker })

def sak_detail(request, sak_id):
    #
    # voteringer over denne saken
    # vis tydelig represententer/partier som 
    # går mot strømmen/er splittet
    # 
    sak = Saker.objects.get(id=sak_id)
    return render_to_response('fylkesperspektiv/sak_detail.html', {'sak': sak})

def oc(request):
    analyse_id = Wnominateanalyser.objects.latest('dato')
    resultater = Wnominateanalyserposisjoner.objects.values('representant', 'analyse', 'representant__parti__id', "representant__fylke__navn", "representant__fornavn", "representant__etternavn").filter(analyse=analyse_id)
    analyser = Wnominateanalyser.objects.all().order_by('-dato')
    ikke_med = Wnominateanalyserposisjoner.objects.values('representant', 'analyse', 'representant__parti__id', "representant__fylke__navn", "representant__fornavn", "representant__etternavn").filter(analyse=analyse_id).filter(x__isnull=True).order_by('representant')
    return render_to_response('fylkesperspektiv/wnominateanalyser.html', {'resultater':resultater, 'ikke_med': ikke_med, 'analyser': analyser })

def oc_detalj(request, analyse_id):
    #Wnominateanalyser, Wnominateanalyserposisjoner
    resultater = Wnominateanalyserposisjoner.objects.values('representant', 'analyse', 'representant__parti__id', "representant__fylke__navn", "representant__fornavn", "representant__etternavn").filter(analyse=analyse_id)
    #resultater = Wnominateanalyserposisjoner.objects.values('representant', 'analyse', 'representant__parti__navn', "representant__fylke__navn", "representant__fornavn", "representant__etternavn").filter(analyse=analyse_id)
    #dir(resultater)
    ikke_med = Wnominateanalyserposisjoner.objects.values('representant', 'analyse', 'representant__parti__id', "representant__fylke__navn", "representant__fornavn", "representant__etternavn").filter(analyse=analyse_id).filter(x__isnull=True).order_by('representant')
    ikke_med2 = Wnominateanalyserposisjoner.objects.values('representant').filter(analyse=analyse_id).filter(x__isnull=True)
    
    #ikke_stats = select *, count(`votering_avgitt`) as c from `fylkesperspektiv_voteringsresultat` group by `representant_id_id`, `votering_avgitt`;
    ikke_stats = Voteringsresultat.objects.values('representant_id', 'votering_avgitt').order_by().annotate(count=Count('votering_avgitt')).filter(representant_id__in=ikke_med2).order_by('representant_id')
    #ikke_stats = Voteringsresultat.objects.filter(representant_id__in=ikke_med2).order_by().annotate(Count('votering_avgitt'))
    analyser = Wnominateanalyser.objects.all().order_by('-dato')
    return render_to_response('fylkesperspektiv/wnominateanalyse_detalj.html', {'ikke_stats':ikke_stats,'ikke_med':ikke_med, 'resultater':resultater, 'analyser': analyser})

def oc_data(request, analyse_id, format):
    if format == 'xml':
        mimetype = 'application/xml'
    if format == 'json':
        mimetype = 'application/javascript'
    #resultater = Wnominateanalyserposisjoner.objects.filter(analyse=analyse_id)
    resultater = Wnominateanalyserposisjoner.objects.values('x', 'y', 'representant', 'analyse', 'representant__parti__id').filter(analyse=analyse_id).filter(x__isnull=False)
    print mimetype, analyse_id, format
    output = json.dumps(list(resultater), cls=DjangoJSONEncoder)
    return HttpResponse(output, mimetype)
    
    # age = Personer.objects.values('etternavn', 'fornavn', 'parti_id', 'foedselsdato', 'doedsdato').annotate(perioder=Count('id'))
    # output = json.dumps(list(age), cls=DjangoJSONEncoder)
    # return HttpResponse(output, mimetype)
    
def sporsmal(request):
    sporsmal = Sporsmal.objects.all().order_by('-datert_dato')
    paginator = Paginator(sporsmal, 25)
    #page = request.GET.get('page')
    try:
        page = int(request.GET.get('page', '1'))
    #except PageNotAnInteger:
        # If page is not an integer, deliver first page.
    #    spor = paginator.page(1)
    #except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
    #    spor = paginator.page(paginator.num_pages)
    except ValueError:
        page = 1
    # If page request (9999) is out of range, deliver last page of results.
    try:
        spor = paginator.page(page)
    except (EmptyPage, InvalidPage):
        spor = paginator.page(paginator.num_pages)

    return render_to_response('fylkesperspektiv/sporsmal.html', {'spor':spor})

def sporsmal_detail(request, sporsmal_id):
    sporsmal = Sporsmal.objects.get(id=sporsmal_id)
    # hvor ofte spørr n nn?
    ivrig = Sporsmal.objects.filter(sporsmal_fra=sporsmal.sporsmal_fra).filter(sporsmal_til=sporsmal.sporsmal_til).order_by('-datert_dato')
    return render_to_response('fylkesperspektiv/sporsmal_detail.html', {'ivrig':ivrig, 'sporsmal': sporsmal})

def sporsmal2(request):
    return render_to_response('fylkesperspektiv/sporsmal2.html')

def whats_new(request, format, days_back=30):
    if format == 'xml':
        mimetype = 'application/xml'
    if format == 'json':
        mimetype = 'application/json; charset=UTF-8'
    if format == 'html':
        mimetype = 'text/html; charset=utf-8'

    today = datetime.date.today()
    thirty_days_ago = today - datetime.timedelta(days=days_back)

    saker = Saker.objects.filter(sist_oppdatert_dato__gte=thirty_days_ago).extra(select={'day' : "date(sist_oppdatert_dato)"}).values('sist_oppdatert_dato').annotate(created_count=Count('id')).order_by('-sist_oppdatert_dato')
    sporsmal_besvart = Sporsmal.objects.filter(besvart_dato__gte=thirty_days_ago).extra(select={"day" : "date(besvart_dato)"}).values('besvart_dato').annotate(created_count=Count('id')).order_by('-besvart_dato')
    sporsmal_sendt = Sporsmal.objects.filter(sendt_dato__gte=thirty_days_ago).extra(select={'day' : "date(sendt_dato)"}).values('sendt_dato').annotate(created_count=Count('id')).order_by('-sendt_dato')
    sporsmal_datert = Sporsmal.objects.filter(datert_dato__gte=thirty_days_ago).extra(select={'day' : "date(datert_dato)"}).values('datert_dato').annotate(created_count=Count('id')).order_by('-datert_dato')
    voteringer = Votering.objects.filter(votering_tid__gte=thirty_days_ago).extra(select={'day' : "date(votering_tid)"}).values('votering_tid').annotate(created_count=Count('votering_id')).order_by('-votering_tid')

    # merger så likt som mulid løsningen question_type_by_year 
    data = list(chain(saker, sporsmal_besvart, sporsmal_sendt,sporsmal_datert, voteringer))
    


    seq = ('saker', 'sporsmal_besvart', 'sporsmal_sendt', 'sporsmal_datert', 'voteringer')
    #val = 0
#    typer = dict.fromkeys(seq, 0)

    ## dict.fromkeys lager bare krøll: http://stackoverflow.com/questions/15516413/dict-fromkeys-all-point-to-same-list?lq=1
    #base = datetime.datetime.today()
    #dateList = dict.fromkeys([ base.date() - datetime.timedelta(days=x) for x in range(0,days_back) ], dict((i, 0) for i in seq))

    #dateList2 = dict(([ base.date() - datetime.timedelta(days=x) for x in range(0,days_back)]  )) # , dict((i, 0) for i in seq)
    #print dateList2

    dateList = {}

    for d in data:
        #print d

        if 'sist_oppdatert_dato' in d:
            if d['sist_oppdatert_dato'] not in dateList:
                dateList[d['sist_oppdatert_dato'].date()] = dict((i, 0) for i in seq)
            dateList[d['sist_oppdatert_dato'].date()]['saker'] = d['created_count']

        if 'besvart_dato' in d:
            if d['besvart_dato'].date() not in dateList:
                dateList[d['besvart_dato'].date()] = dict((i, 0) for i in seq)
            dateList[d['besvart_dato'].date()]['sporsmal_besvart'] = d['created_count']            

        if 'votering_tid' in d:
            if d['votering_tid'].date() not in dateList:
                dateList[d['votering_tid'].date()] = dict((i, 0) for i in seq)
            dateList[d['votering_tid'].date()]['voteringer'] = d['created_count']

        if 'datert_dato' in d:
            if d['datert_dato'].date() not in dateList:
                dateList[d['datert_dato'].date()] = dict((i, 0) for i in seq)
            dateList[d['datert_dato'].date()]['sporsmal_datert'] = d['created_count']

        if 'sendt_dato' in d:
            if d['sendt_dato'].date() not in dateList:
                dateList[d['sendt_dato'].date()] = dict((i, 0) for i in seq)
            dateList[d['sendt_dato'].date()]['sporsmal_sendt'] = d['created_count']

    # make sure all dates are in
    base = datetime.datetime.today()
    dates = [ base.date() - datetime.timedelta(days=x) for x in range(0,days_back) ]
    for date in dates:
        if date not in dateList:
            dateList[date] = dict((i, 0) for i in seq)  # add the missing dates
        #print date

    #print dateList, len(dateList)
    # for i in dateList:
    #     print i, dateList[i]

    flat = list(dateList)
    flat.sort()
    data = []

    for key in flat:
        data.append((key, dateList[key]))

    # only do json dumps if format is json or xml
    if format != 'html':
        output = json.dumps(data, cls=DjangoJSONEncoder)
        return HttpResponse(output, mimetype)
    else:
        # return normal
        #return HttpResponse(data, mimetype)
        return data

def aktivitetstopper(request): 
    # arg http://stackoverflow.com/questions/2909869/error-while-executing-query
    from django.db import connection
    cursor = connection.cursor()

    cursor.execute("SELECT CONCAT(YEAR(votering_tid), ' ', MONTHNAME(votering_tid)) as tid, count(*) as antall FROM `fylkesperspektiv_votering` GROUP BY YEAR(`votering_tid`), MONTH(`votering_tid`)")
    voteringer_maaned_aar = cursor.fetchall()
    #voteringer_maaned_aar = Votering.objects.raw("SELECT CONCAT(YEAR(votering_tid), ' ', MONTHNAME(votering_tid)) as tid, count(*) as antall FROM `fylkesperspektiv_votering` GROUP BY YEAR(`votering_tid`), MONTH(`votering_tid`)") 
    # print str(Questions.objects.filter(sesjonid='2011-2012').values('sporsmal_til', 'sporsmal_fra').annotate(count=Count('sporsmal_til')).query)
    #SELECT *, CONCAT(YEAR(votering_tid), ' ', MONTHNAME(votering_tid)) as tid, count(*) as antall FROM `fylkesperspektiv_votering` GROUP BY YEAR(`votering_tid`), MONTH(`votering_tid`);


    cursor.execute("SELECT sist_oppdatert_dato, count(*) AS antall FROM fylkesperspektiv_saker GROUP BY YEAR(sist_oppdatert_dato), MONTH(sist_oppdatert_dato)")
    saker_maaned_aar = cursor.fetchall()
    #saker_maaned_aar = Saker.objects.raw("SELECT sist_oppdatert_dato, count(*) AS antall FROM fylkesperspektiv_saker GROUP BY YEAR(sist_oppdatert_dato), MONTH(sist_oppdatert_dato)")

    # øker antallet saker?
    cursor.execute("SELECT YEAR(sist_oppdatert_dato), count(*) AS antall FROM fylkesperspektiv_saker GROUP BY YEAR(sist_oppdatert_dato)")
    saker_aar = cursor.fetchall()

    new_stuff = whats_new(request, 'html', days_back=30)

    return render_to_response('fylkesperspektiv/aktivitetstopper.html', {'voteringer_maaned_aar': voteringer_maaned_aar, 'saker_maaned_aar': saker_maaned_aar, 'saker_aar':saker_aar,'new_stuff': new_stuff})



def question_type_by_year(request, format):
    if format == 'xml':
        mimetype = 'application/xml'
    if format == 'json':
        mimetype = 'application/json; charset=UTF-8'
    
    # SELECT `sesjonid_id`, type, count(*) as c from `fylkesperspektiv_sporsmal` group by `sesjonid_id`, type order by sesjonid_id asc;
    sporsmal = Sporsmal.objects.values('sesjonid', 'type').order_by('sesjonid').annotate(Count('sesjonid'), Count('type'))
    
    cathegories = set([s['type'] for s in sporsmal])
    
    values = dict.fromkeys(cathegories)
    #years3 = dict.fromkeys(session)          #defaultdict(dict)
    years3 = {}
    for s in sporsmal:
        if s['sesjonid'] not in years3:           # add year
            years3[s['sesjonid']] = values.copy()
        years3[s['sesjonid']][s['type']] = s['sesjonid__count']
    #print years3

    y = list(years3)
    y.sort()    
    data = []
    for key in y:
        data.append((key, years3[key]))
    #print data

    output = json.dumps(data, cls=DjangoJSONEncoder)
    return HttpResponse(output, mimetype)


def komite(request, kom_id):
    komite = Komiteer.objects.get(id=kom_id) 
    personer = Personer.objects.filter(komiteer__id=kom_id).select_related()
    saker = Saker.objects.filter(komite=kom_id).filter(Q(behandlet_sesjon_id=functions.get_current_session_nr()) | Q(behandlet_sesjon_id__exact='')).order_by('-sist_oppdatert_dato').select_related()
    
    # stemmer medlemmene av komiteen for saker de selv har behandlet?
    saker_som_er_votert_over = Saker.objects.filter(komite=kom_id, status='behandlet', sist_oppdatert_dato__gt='2009-11-17 00:00:00')
    print saker_som_er_votert_over
    #print functions.get_current_session_nr()
    #medlemskap = KomiteeMedlemskap.objects.filter(komitee=kom_id) # redundant 

    votering = Votering.objects.filter(sak__in=saker).order_by('-votering_tid')
    return render_to_response('fylkesperspektiv/komite.html', {'votering':votering, 'saker': saker, 'personer':personer, 'komite': komite})

@csrf_exempt
def sporsmal_detail_data(request):
    #csrf(request)
    # denne brukes bare til å få detaljer om en person via ajax, stemmer?

    if request.method == "POST":
        pid = request.POST['person_id']
        sesjon = Sesjoner.objects.get(er_innevaerende=True)
        person = Personer.objects.get(id=pid)
        #data = Sporsmal.objects.filter(Q(sporsmal_fra=pid ) | Q(sporsmal_til=pid)).filter(sesjonid=sesjon)

        #temp_ut_dict = defaultdict(list)
        #temp_inn_dict = defaultdict(list)
        stiller = Sporsmal.objects.filter(sporsmal_fra=pid).filter(sesjonid=sesjon)
        blir_stillt = Sporsmal.objects.filter(sporsmal_til=pid).filter(sesjonid=sesjon)


        persondata = {
            'navn':person.fornavn +" "+ person.etternavn, 
            'id': person.id, 
            'parti': str(person.parti),
            'fylke': str(person.fylke)
            }

        # for d in data:
        #     #print d.sporsmal_fra.id, pid 
        #     if d.sporsmal_fra.id == pid:
        #         #print "ut"
        #         temp_ut_dict[d.sporsmal_til_id].append([str(d.sporsmal_til), d.sporsmal_til.id, d.id, d.tittel])

        #     if d.sporsmal_til.id == pid:
        #         #print "inn"
        #         temp_inn_dict[d.sporsmal_fra.id].append([str(d.sporsmal_fra), d.sporsmal_fra.id, d.id, d.tittel])
        
            #print temp_dict #len(inn), len(ut)
    #print temp_ut_dict, temp_inn_dict
    #return HttpResponse(json.dumps({'person': persondata, 'inn': temp_inn_dict, 'ut' : temp_ut_dict}), mimetype='application/javascript')
    return HttpResponse(json.dumps({'person': persondata, 'stiller': len(stiller), 'blir_stillt': len(blir_stillt), 'sesjon':str(sesjon)}), mimetype='application/javascript')


def question_json2(request, format):
    # denne lager data til kant-grafen 
    if format == 'xml':
        mimetype = 'application/xml'
    if format == 'json':
        mimetype = 'application/json; charset=UTF-8'
        #mimetype = 'application/javascript'

    # denne sesjonen...
    sesjon = Sesjoner.objects.get(er_innevaerende=True)

    links = Sporsmal.objects.filter(sesjonid=sesjon).extra(select={'target': 'sporsmal_til_id', 'source': 'sporsmal_fra_id'}).values('target', 'source').annotate(value=Count('sporsmal_til'))
    #print links
    big_askers = defaultdict(dict)      # lager en dic med hvem som får spørsmål og hvor mange
    innvolved_reps = []
    
    for l in links:
        big_askers[l['source']][l['target']] = l['value']
        innvolved_reps.append(l['source'])
        innvolved_reps.append(l['target'])        
    innvolved_reps = list(set(innvolved_reps)) # lager set for å få kun uniqe
    #print innvolved_reps
    #print big_askers
    
    nodes = Personer.objects.filter(id__in=innvolved_reps).extra(select={'group': 'parti_id', 'name': 'id'}).values('fornavn', 'etternavn', 'group', 'name')
    
    data = []
    for n in nodes:
        #print n
        person = {}
        person['full_name'] = n['fornavn'] + ' ' + n['etternavn'] 
        person['name'] = n['name']
        person['parti'] = n['group']
        
        #print person['name'], big_askers[person['name']], sum(big_askers[person['name']].values())

        person['size'] = sum(big_askers[person['name']].values())
        person['imports'] = big_askers[person['name']]
        data.append(person)
    #print data
    output = json.dumps(data, cls=DjangoJSONEncoder)
    #print output
    return HttpResponse(output, mimetype)
    
    

def question_json(request, format):
#if request.is_ajax():
    if format == 'xml':
        mimetype = 'application/xml'
    if format == 'json':
        mimetype = 'application/javascript'
    
    
    #links = Sporsmal.objects.filter(sesjonid='2011-2012').values('sporsmal_til', 'sporsmal_fra').annotate(count=Count('sporsmal_til'))
    #SELECT sporsmal_fra_id, sporsmal_til_id, count(sporsmal_til_id) as count FROM fylkesperspektiv_sporsmal WHERE sesjonid_id = '2011-2012' GROUP BY sporsmal_fra_id, sporsmal_til_id order by count desc
    links = Sporsmal.objects.filter(sesjonid='2011-2012').extra(select={'target': 'sporsmal_til_id', 'source': 'sporsmal_fra_id'}).values('target', 'source').annotate(value=Count('sporsmal_til'))
    
    #links = Sporsmal.objects.filter(sesjonid='2011-2012').extra(select={'target': 'sporsmal_til_id', 'source': 'sporsmal_fra_id'}).values('target', 'source').annotate(value=Count('sporsmal_til_id'))
    
    #print links
    innvolved_reps = []
    for l in links:
        innvolved_reps.append(l['source'])
        innvolved_reps.append(l['target'])        
    innvolved_reps = list(set(innvolved_reps)) # lager set for å få kun uniqe
    #print innvolved_reps
    
    #nodes = Dagensrepresentanter.objects.all().extra(select={'group': 'parti', 'name': 'id'}).values('fornavn', 'etternavn', 'group', 'name')    # values gjør objectet til en dict
    # måtte hente dette fra Representanter, da det dukket opp en del som ikke fantes i Dagensrepresentanter .. rart, men sant.

    nodes = Personer.objects.filter(id__in=innvolved_reps).extra(select={'group': 'parti_id', 'name': 'id'}).values('fornavn', 'etternavn', 'group', 'name') 

    # .extra(select={'target': 'sporsmal_til'})
    nodes_and_links = {
        'nodes' : list(nodes),
        'links' : list(links)
    }
        
    #result_list = list(chain(nodes, links)) # slik joiner man to querysets 
    
    #data = serializers.serialize(format, nodes_and_links) # serializers serialiserer django spørringer. trenger json.dumps() for å mekke på vanlige python strukturer.
    output = json.dumps(nodes_and_links, cls=DjangoJSONEncoder)
    print output
    return HttpResponse(output, mimetype)
    
    #return HttpResponse( simplejson.dumps(nodes_and_links),mimetype )

    # #return HttpResponse(simplejson.dumps(nodes), mimetype='application/json')
    # return render_to_response(simplejson.dumps(nodes), mimetype='application/json')





#
# hva gjorde denne? (utgår)
#
# def votering(request):
#     # paginator  https://docs.djangoproject.com/en/dev/topics/pagination/?from=olddocs#example
#     votering_liste = Votering.objects.all().order_by('-votering_tid')
#     paginator = Paginator(votering_liste, 25)                               # Show 25 contacts per page
    
#     try:                                                                    # Make sure page request is an int. If not, deliver first page. 
#         page = int(request.GET.get('page', '1'))
#     except ValueError:
#         page = 1                                                            # If page request (9999) is out of range, deliver last page of results.
#     try:
#         votering = paginator.page(page)
#     except (EmptyPage, InvalidPage):
#         votering = paginator.page(paginator.num_pages)
#     #print votering
#     return render_to_response("fylkesperspektiv/votering.html", {"votering": votering })   
#     #return render_to_response("fylkesperspektiv/votering.html", {'votering': votering_liste})

#
# hva gjorde denne? (utgår)
#
# def avstemninger(request):
#     res = Voteringsresultat.objects.values('votering', 'representant_id', 'votering_avgitt', 'representant_id__parti__id')[:170]
#     resultater = {}
#     resultater = defaultdict(defaultdict)   #defaultdict importeres øverst
#     for r in res:
#         print r['votering'], r['representant_id']
#         resultater[r['votering']][r['representant_id']] = {'vot': r['votering_avgitt'], 'parti': r['representant_id__parti__id'] }
#     #print resultater    
#     return render_to_response('fylkesperspektiv/avstemninger.html', {'res': res, 'resultater': dict(resultater)})
    
    
#
#  scatterplot utgår
#
# def scatter(request):
#     return render_to_response('fylkesperspektiv/scatter.html')

# def age_scatter(request, format):
#     if format == 'xml':
#         mimetype = 'application/xml'
#     if format == 'json':
#         mimetype = 'application/javascript'
#     age = Personer.objects.values('etternavn', 'fornavn', 'parti_id', 'foedselsdato', 'doedsdato').annotate(perioder=Count('id')).filter(doedsdato='0001-01-01 00:00:00')
#     output = json.dumps(list(age), cls=DjangoJSONEncoder)
#     return HttpResponse(output, mimetype)
    

# def komiteer(request):
#     # query over ManyToMany field
#     dagensrep_kommiteer = Representanter.objects.values('komiteer')        
#     dagens_komiteer = Komiteer.objects.filter(id__in=dagensrep_kommiteer).distinct()
#     return render_to_response('fylkesperspektiv/komiteer.html', {'dagens_komiteer': dagens_komiteer})






#.distinct("besvart_av")
# .count() .exists() 
# Sporsmal.objects.filter()
# Sporsmal.objects.get() one
# .values('title', 'created')
# .order_by(-field) # minus is desc
# Sporsmal.objects.filter(published=True, created__gt=datetime(2012,1,8,18,38)) # gt & lt
#print str(Sporsmal.objects.filter(sesjonid="2011-2012").distinct(besvart_av).query)

#print str(Sporsmal.objects.filter(sesjonid='2011-2012').values('sporsmal_til', 'besvart_av').annotate(num_authors=Count('besvart_av')).query)
# SELECT sporsmal_til, besvart_av, count(*)
# from sporsmal
# WHERE sesjonid='2011-2012'
# group by 1, 2;








# https://docs.djangoproject.com/en/dev/howto/outputting-csv/


# def to_csv_export(request):
#     # Create the HttpResponse object with the appropriate CSV header.
#     response = HttpResponse(content_type='text/csv')
#     response['Content-Disposition'] = 'attachment; filename="somefilename.csv"'

#     writer = csv.writer(response)
#     writer.writerow(['First row', 'Foo', 'Bar', 'Baz'])
#     writer.writerow(['Second row', 'A', 'B', 'C', '"Testing"', "Here's a quote"])

#     return response


# http://djangosnippets.org/snippets/2233/ alternative: http://djangosnippets.org/snippets/911/
# import xlwt

# def tool_excel_export(self, request, obj, button):
#     'http://djangosnippets.org/snippets/2233/'
#     response = HttpResponse(mimetype="application/ms-excel")
#     response['Content-Disposition'] = 'attachment; filename=file.xls'
    
#     wb = xlwt.Workbook()
#     ws = wb.add_sheet('Sheetname')
    
#     ws.write(0, 0, 'Firstname')
#     ws.write(0, 1, 'Surname')
#     ws.write(1, 0, 'Hans')
#     ws.write(1, 1, 'Muster')

#     wb.save(response)
#     return response 





# def create_question_table(request):
#     ##Entry.objects.extra(select={'is_recent': "pub_date > '2006-01-01'"})
    
#     #sporsmal = Sporsmal.objects.values('besvart_av', 'besvart_av_minister_tittel', 'datert_dato', 'sporsmal_fra__etternavn', 'sporsmal_fra__fornavn', 'sporsmal_til__etternavn', 'sporsmal_til__fornavn', 'tittel', 'type')    
#     #sporsmal = Sporsmal.objects.values( 'datert_dato', 'tittel', 'type', 'sporsmal_fra__etternavn')
#     pass

