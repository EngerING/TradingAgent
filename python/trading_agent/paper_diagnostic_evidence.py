"""Evidence from one owned Paper round trip; missing observations remain null."""
from .paper_lab import num,date

def evidence(o):
    fills=list(o['fills'].values());fees=o['commissions'];initial=o.get('initial_snapshot');opened=o.get('opening_snapshot');final=o.get('final_snapshot')
    def seconds(later,earlier):
        if not later or not earlier:return None
        value=(date(later)-date(earlier)).total_seconds()
        return value if value>=0 else None
    def side(name):
        rows=[f for f in fills if f['side']==name];q=sum((num(f['quantity']) for f in rows),num(0))
        reports=[fees[f['exec_id']] for f in rows if f['exec_id'] in fees]
        complete=bool(rows) and len(reports)==len(rows);currencies=sorted({r['currency'] for r in reports})
        amount=sum((num(r['amount']) for r in reports),num(0)) if complete and len(currencies)==1 else None
        requested=[]
        for f in rows:
            recovery=o.get('recovery_orders',{}).get(str(f['order_id']))
            price=o.get('fill_request_prices',{}).get(f['exec_id'])
            if price is None:price=recovery['price'] if recovery else o['entry'] if name=='BUY' else o['stop'] if f['order_id']==o['order_ids'][2] else o.get('close_requested_price',o['target'])
            requested.append({'exec_id':f['exec_id'],'order_id':f['order_id'],'price':str(num(price)),
                'quantity':f['quantity'],'limit_difference_adverse':str((num(f['price'])-num(price))*(1 if name=='BUY' else -1)),
                'recovery_reference':recovery['reference'] if recovery else None,
                'recovery_requested_at':recovery['sent_at'] if recovery else None,'recovery_quote':recovery['quote'] if recovery else None})
        first=min(rows,key=lambda f:date(f['at'])) if rows else None
        sent=o['sent_at'] if name=='BUY' else o.get('close_requested_at',o['sent_at'])
        first_recovery=o.get('recovery_orders',{}).get(str(first['order_id'])) if first else None
        if first_recovery:sent=first_recovery['sent_at']
        executed=sum((num(f['quantity'])*num(f['price']) for f in rows),num(0))/q if q else None
        quote=o.get('quote') if name=='BUY' else o.get('closing_quote')
        if first_recovery:quote=first_recovery['quote'] if len({f['order_id'] for f in rows})==1 else None
        arrival=num(quote['ask' if name=='BUY' else 'bid']) if quote else None
        slip=(executed-arrival)*(1 if name=='BUY' else -1) if executed is not None and arrival is not None else None
        return {'executed_quantity_eur':str(q),'executed_vwap':str(executed) if executed is not None else None,
            'requested_price':o['entry'] if name=='BUY' else o.get('close_requested_price') or (requested[0]['price'] if requested and len({x['price'] for x in requested})==1 else None),
            'requested_at':sent,'request_prices_by_fill':requested,'commission':str(amount) if amount is not None else None,
            'commission_currency':currencies[0] if complete and len(currencies)==1 else None,
            'commissions_complete':complete,'commission_reports':reports,'arrival_quote':quote,
            'slippage_adverse_per_eur':str(slip) if slip is not None else None,
            'slippage_adverse_usd':str(slip*q) if slip is not None else None,
            'first_fill_received_at':first['at'] if first else None,'first_fill_broker_at':first.get('broker_at') if first else None,
            'time_until_first_fill_received_seconds':seconds(first['at'],sent) if first else None,
            'time_until_first_fill_broker_seconds':seconds(first.get('broker_at'),sent) if first else None}
    buy,sell=side('BUY'),side('SELL');balanced=num(buy['executed_quantity_eur'])>0 and num(buy['executed_quantity_eur'])==num(sell['executed_quantity_eur'])
    gross=sum((num(f['quantity'])*num(f['price'])*(1 if f['side']=='SELL' else -1) for f in fills),num(0)) if balanced else None
    known=balanced and all(f['exec_id'] in fees and fees[f['exec_id']]['currency']=='USD' and num(fees[f['exec_id']]['amount'])>=0 for f in fills)
    net=gross-sum((num(fees[f['exec_id']]['amount']) for f in fills),num(0)) if known else None
    position=lambda s:None if s is None else {'eur_cash':s.get('eur_cash'),'positions':s.get('positions'),
        'portfolio':s.get('portfolio'),'queries_complete':s.get('exposure_reads_complete'),'cash_reconciliation':s.get('cash_reconciliation')}
    return {'schema_version':2,'environment':'PAPER_TRADING','category':'EXECUTION_DIAGNOSTICS','strategy_result':False,
        'instrument':{'symbol':'EUR','currency':'USD','security_type':'CASH','exchange':'IDEALPRO','contract_id':12087792},
        'intent':o['intent'],'session_id':o['session_id'],'state':o['state'],'requested_quantity_eur':o['quantity'],
        'estimated_risk_usd':o.get('diagnostic_estimated_risk_usd'),'cost_estimate_status':o.get('diagnostic_cost_estimate_status'),
        'buy':buy,'sell':sell,'margin_before':o.get('margin_before'),'margin_after_open':opened.get('initial_margin') if opened else None,
        'margin_after_close':final.get('initial_margin') if final else None,
        'observed_opening_spread':str(num(o['quote']['ask'])-num(o['quote']['bid'])),
        'observed_closing_spread':str(num(o['closing_quote']['ask'])-num(o['closing_quote']['bid'])) if o.get('closing_quote') else None,
        'contract_metadata':o.get('contract_evidence'),'odd_lot_candidate':num(o['quantity'])<20000,
        'odd_lot_result':'SIMULATED_FILL_OBSERVED_ROUTING_NOT_CERTIFIED' if fills else 'NOT_OBSERVED',
        'errors_restrictions':o['incidents'],'api_events':o.get('api_events',[]),
        'position_before_open':position(initial),'position_after_open':position(opened),'position_after_close':position(final),
        'final_open_orders':final.get('orders') if final else None,'gross_pnl_usd':str(gross) if gross is not None else None,
        'net_pnl_usd':str(net) if net is not None else None,'close_requested_at':o.get('close_requested_at'),
        'close_deadline_at':o.get('close_deadline_at'),'opening_fill_received_at':o.get('first_open_fill_received_at'),
        'initial_eur_uncertainty':o.get('initial_eur_uncertainty'),'strict_post_reconciled_at':o.get('post_eur_reconciled_at'),
        'recovery_close_only':bool(o.get('recovery_order_ids')),'recovery_orders':o.get('recovery_orders',{}),
        'limitations':['Paper fills/fees are simulated, not verified Live costs.',
            'Receipt latency differs from broker execution latency; unknown broker clock remains null.',
            'Slippage uses arrival quote only when recorded; protective exits without that quote remain null.',
            'A Paper fill below the IDEALPRO minimum does not certify Live odd-lot execution.',
            'Flat or unchanged margin does not establish a margin rate; account-specific restrictions remain unverified.']}
