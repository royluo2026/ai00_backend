// Run with the Connector's Java 11 Nashorn, without credentials or a TC connection.
var Files=Java.type('java.nio.file.Files'),Paths=Java.type('java.nio.file.Paths');
var source=String(new (Java.type('java.lang.String'))(Files.readAllBytes(Paths.get(arguments[0])),'UTF-8'));
var start=source.indexOf('function fileByteSize(');
eval(source.substring(start,source.indexOf('\nfunction ',start+1)));
function observationTiming(){}
function fail(code){throw Error(code);}
function object(value){return {getUid:function(){return 'test-file';},getPropertyObject:function(name){
 if(name!=='byte_size')throw Error('wrong_property');
 return {getStringValue:function(){return value;}};
}};}
if(fileByteSize(object('564224'))!==564224)throw Error('incorrect_byte_count');
if(fileByteSize(object('9007199254740991'))!==9007199254740991)throw Error('incorrect_maximum');
['0','9007199254740992','551 Kb','1.5',''].forEach(function(value){
 var rejected=false;try{fileByteSize(object(value));}catch(error){rejected=String(error).indexOf('teamcenter_file_size_')>=0;}
 if(!rejected)throw Error('invalid_size_accepted:'+value);
});
print('Nashorn byte_size validation: PASS');
