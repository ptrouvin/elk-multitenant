# elk-multitenant
ELK design add-on to obtain real multi-tenancy in cloud ready environment

<p>A way to segregate logs entries inside ELK with OAUTH authentication:</p>
<p> </p>
<p> ELK: Elasticsearch, Logstash, Kibana, suffers of a lack of real multi-tenancy solution when used in large cloud environment.</p>
<p>I mean, how to guaranty to a customer that his logs will never be delivered to someone else?</p>
<p> </p>
<p>You can not do that with <strong>shield</strong>, the ELK commercial tool. With shield you can add user authentication and define who can access to which fields. So the strength of this solution is based on configuration.</p>
<p> </p>
<p>The solution I've though and built, can guaranty by design that logs of a customer will never be accessible by another.</p>
<p>The main idea is to use the elasticsearch index structure to store data per customer, let's say a CID: Customer Id.</p>
<p> </p>
<p>When logs entries are treated by logstash, if there is a CID field, then it is used to determine the elasticsearch index to use.</p>
<p>If there is no CID field, then the entry is processed by a rule processor which try to determine the CID.</p>
<p>Rules can be based on any JSON fields regex combination, things like if entry comes from this IP address then set CID to ...</p>
<p> </p>
<p>And then on the other side, because elasticsearch index are customer based, inside kibana you can be sure that none can access logs of another one.</p>
<p>How: I've added a nginx proxy with OAUTHv2 capabilities to handle user authentication and the CID must be read from. (user LDAP attribute, or whatever).</p>
<p> </p>
<p><img src="http://www.o4s.fr/images/LaaS-Archi.png" alt="Log As A Service Architecture" width="303" height="306" /> </p>
<p> </p>
<p> </p>
<p> </p>